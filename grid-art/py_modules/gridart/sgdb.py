"""SteamGridDB API v2 client (https://www.steamgriddb.com/api/v2).

Everything here runs only when the user opens the artwork browser or applies a picture:
no background work. API answers are kept in a small in-memory cache for the session so
flipping between tabs or pages doesn't hit the API again. Certificate checks are never
disabled; downloads are limited to SteamGridDB's own hosts and a size cap.
"""
import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.steamgriddb.com/api/v2"
UA = "grid-art-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"
API_HOSTS = ("www.steamgriddb.com",)
# Image CDN hosts SteamGridDB serves full-size files from.
IMG_SUFFIX = ".steamgriddb.com"
MAX_IMAGE = 25 * 1024 * 1024
MAX_JSON = 2_000_000

KINDS = ("grids", "heroes", "logos", "icons")
STYLES = {
    "grids": ("alternate", "blurred", "white_logo", "material", "no_logo"),
    "heroes": ("alternate", "blurred", "material"),
    "logos": ("official", "white", "black", "custom"),
    "icons": ("official", "custom"),
}
# Shapes Steam actually uses; anything else gets cropped/letterboxed in the library.
DIMENSIONS = {
    "capsule": "600x900,342x482,660x930",
    "wide": "460x215,920x430",
}

_CA_FILES = ("/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")
_ctx = None
_cache: dict = {}
CACHE_TTL = 600
CACHE_MAX = 64


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def context() -> ssl.SSLContext:
    global _ctx
    if _ctx:
        return _ctx
    try:
        import certifi  # type: ignore
        _ctx = ssl.create_default_context(cafile=certifi.where())
        return _ctx
    except Exception:
        pass
    for f in _CA_FILES:
        if os.path.exists(f):
            _ctx = ssl.create_default_context(cafile=f)
            return _ctx
    _ctx = ssl.create_default_context()
    return _ctx


def _host_ok(url: str, api: bool) -> bool:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not u.hostname:
        return False
    if api:
        return u.hostname in API_HOSTS
    return u.hostname == "steamgriddb.com" or u.hostname.endswith(IMG_SUFFIX)


def _opener(api: bool):
    class _Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not _host_ok(newurl, api):
                raise ApiError(f"refusing redirect to {newurl}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context()), _Redirect())


def _read(url: str, headers: dict, max_bytes: int, api: bool, timeout: float = 15) -> tuple:
    if not _host_ok(url, api):
        raise ApiError(f"refusing URL outside SteamGridDB: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    with _opener(api).open(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
        ctype = r.headers.get("Content-Type", "")
    if len(data) > max_bytes:
        raise ApiError("file is too large")
    return data, ctype


def build_query(kind: str, *, styles=(), dimensions: str = "", animated: bool = False,
                nsfw: bool = False, humor: bool = True, epilepsy: bool = True, page: int = 0) -> str:
    q = {"page": str(max(0, int(page)))}
    st = [s for s in styles if s in STYLES.get(kind, ())]
    if st:
        q["styles"] = ",".join(st)
    if dimensions and kind == "grids":
        q["dimensions"] = dimensions
    # Steam only takes PNG or JPEG custom art; animated art is only usable as APNG.
    if kind == "icons":
        q["mimes"] = "image/png"
    elif animated:
        q["types"] = "animated"
        q["mimes"] = "image/png"
    else:
        q["types"] = "static"
        q["mimes"] = "image/png" if kind == "logos" else "image/png,image/jpeg"
    q["nsfw"] = "any" if nsfw else "false"
    q["humor"] = "any" if humor else "false"
    q["epilepsy"] = "any" if epilepsy else "false"
    return urllib.parse.urlencode(q, safe=",")


def api_get(path: str, key: str, use_cache: bool = True):
    """GET API + path; returns the parsed `data` field. Raises ApiError with a readable message."""
    if not key:
        raise ApiError("No SteamGridDB API key set", 401)
    now = time.monotonic()
    hit = _cache.get(path)
    if use_cache and hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        raw, _ = _read(API + path, {"Authorization": f"Bearer {key}", "Accept": "application/json"}, MAX_JSON, True)
    except urllib.error.HTTPError as e:
        msg = {401: "SteamGridDB rejected the API key", 403: "SteamGridDB rejected the API key",
               404: "SteamGridDB has no entry for this game", 429: "SteamGridDB rate limit, try again in a minute"}
        try:
            body = json.loads(e.read(MAX_JSON).decode("utf-8"))
            errs = ", ".join(body.get("errors") or [])
        except Exception:
            errs = ""
        raise ApiError(msg.get(e.code) or errs or f"SteamGridDB error {e.code}", e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach SteamGridDB ({getattr(e, 'reason', e)})") from None
    except TimeoutError:
        raise ApiError("SteamGridDB took too long to answer") from None
    body = json.loads(raw.decode("utf-8"))
    if not body.get("success", False):
        raise ApiError(", ".join(body.get("errors") or []) or "SteamGridDB returned an error")
    data = body.get("data")
    if len(_cache) >= CACHE_MAX:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    _cache[path] = (now, data)
    return data


def clear_cache():
    _cache.clear()


def slim(item: dict) -> dict:
    """Only what the browser shows; keeps the bridge traffic small."""
    a = item.get("author") or {}
    return {
        "id": item.get("id"),
        "url": item.get("url", ""),
        "thumb": item.get("thumb") or item.get("url", ""),
        "width": item.get("width") or 0,
        "height": item.get("height") or 0,
        "style": item.get("style", ""),
        "mime": item.get("mime", ""),
        "score": item.get("score") or 0,
        "nsfw": bool(item.get("nsfw")),
        "humor": bool(item.get("humor")),
        "epilepsy": bool(item.get("epilepsy")),
        "author": a.get("name", ""),
    }


def assets(kind: str, key: str, *, appid: int = 0, game_id: int = 0, query: str = "") -> list:
    if kind not in KINDS:
        raise ApiError(f"unknown artwork type {kind}")
    target = f"game/{int(game_id)}" if game_id else f"steam/{int(appid)}"
    data = api_get(f"/{kind}/{target}?{query}", key) or []
    return [slim(x) for x in data if x.get("url")]


# A typed search term shows art from this many of its best-matching games at once.
MAX_TERM_GAMES = 5


def interleave(lists: list) -> list:
    """Round-robin merge (first of each list, then second of each...), dropping repeated ids."""
    out, seen = [], set()
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst) and lst[i].get("id") not in seen:
                seen.add(lst[i].get("id"))
                out.append(lst[i])
    return out


def search(term: str, key: str) -> list:
    term = (term or "").strip()
    if not term:
        return []
    # The autocomplete route wants the term URL-encoded twice (a single encode breaks on '/' etc).
    enc = urllib.parse.quote(urllib.parse.quote(term, safe=""), safe="")
    data = api_get(f"/search/autocomplete/{enc}", key) or []
    return [{"id": g.get("id"), "name": g.get("name", ""), "verified": bool(g.get("verified")),
             "year": time.gmtime(g["release_date"]).tm_year if g.get("release_date") else None}
            for g in data if g.get("id")][:12]


def image_type(data: bytes) -> str:
    """'png' | 'jpg' | '' from the file's magic bytes (never trust the extension)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return ""


def download(url: str) -> dict:
    """Full-size image as base64 + Steam's type name ('png' | 'jpg')."""
    try:
        data, ctype = _read(url, {"Accept": "image/png,image/jpeg"}, MAX_IMAGE, False, timeout=30)
    except urllib.error.HTTPError as e:
        raise ApiError(f"Download failed ({e.code})") from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach SteamGridDB ({getattr(e, 'reason', e)})") from None
    ext = image_type(data)
    if not ext:
        raise ApiError(f"Steam only takes PNG or JPEG artwork (got {ctype or 'unknown type'})")
    return {"data": base64.b64encode(data).decode("ascii"), "ext": ext, "bytes": len(data), "raw": data}
