"""itch.io API client (https://api.itch.io, the API the official itch app and butler use).

Signs in with the user's own itch.io API key (itch.io → Settings → API keys), sent in the
Authorization header and never to any other host. Only runs when the plugin asks: there is no
background polling. Certificate checks are never disabled.
"""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.itch.io"
UA = "itch-library-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"
MAX_JSON = 8_000_000
MAX_COVER = 8 * 1024 * 1024
PER_PAGE = 100
MAX_PAGES = 100          # 10 000 owned games is plenty

_CA_FILES = ("/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")
_ctx = None

# Upload types that are something you run. Soundtracks, books, assets etc. are left out.
PLAYABLE_TYPES = ("default", "")
# What the library shows by default (itch page classification).
GAME_CLASSES = ("game", "tool", "")


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed by hand so the API key never goes to the download CDN."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(follow: bool):
    handlers = [urllib.request.HTTPSHandler(context=context())]
    if not follow:
        handlers.append(_NoRedirect())
    return urllib.request.build_opener(*handlers)


def _https(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" and bool(u.hostname)


def _api_url(path: str, params: dict | None = None) -> str:
    q = {k: v for k, v in (params or {}).items() if v not in (None, "", 0)}
    return f"{API}{path}" + (f"?{urllib.parse.urlencode(q)}" if q else "")


def _headers(key: str) -> dict:
    return {"User-Agent": UA, "Authorization": key, "Accept": "application/vnd.itch.v2", "Accept-Language": "*"}


def _message(body: bytes, status: int) -> str:
    try:
        d = json.loads(body.decode("utf-8", "replace"))
        errs = d.get("errors") if isinstance(d, dict) else None
        if isinstance(errs, list) and errs:
            return "; ".join(str(e) for e in errs[:3])
    except Exception:
        pass
    if status in (401, 403):
        return "itch.io rejected the API key"
    if status == 404:
        return "itch.io doesn't have that (removed, or not yours)"
    if status == 429:
        return "itch.io asked us to slow down; try again in a minute"
    return f"itch.io answered HTTP {status}"


def get(path: str, key: str, params: dict | None = None, timeout: float = 20) -> dict:
    if not key:
        raise ApiError("Not signed in", 401)
    req = urllib.request.Request(_api_url(path, params), headers=_headers(key))
    try:
        with _opener(True).open(req, timeout=timeout) as r:
            data = r.read(MAX_JSON + 1)
    except urllib.error.HTTPError as e:
        raise ApiError(_message(e.read(4096), e.code), e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach itch.io ({getattr(e, 'reason', e)})") from None
    except TimeoutError:
        raise ApiError("itch.io didn't answer in time") from None
    if len(data) > MAX_JSON:
        raise ApiError("itch.io sent an unexpectedly large answer")
    try:
        d = json.loads(data.decode("utf-8"))
    except ValueError:
        raise ApiError("itch.io sent something that isn't JSON") from None
    if isinstance(d, dict) and d.get("errors"):
        # The API sometimes answers 200 with an errors list (e.g. an invalid key).
        msg = "; ".join(str(e) for e in d["errors"][:3])
        raise ApiError(msg, 401 if "key" in msg.lower() else 400)
    if not isinstance(d, dict):
        raise ApiError("itch.io sent an unexpected answer")
    return d


# ------------------------------------------------------------------ shapes

def _traits(obj: dict) -> set:
    t = obj.get("traits")
    if isinstance(t, list):
        return {str(x) for x in t}
    # Older answers carried booleans instead of a traits list.
    return {k for k in ("p_windows", "p_linux", "p_osx", "p_android", "demo", "preorder") if obj.get(k)}


def platforms(obj: dict) -> list:
    t = _traits(obj)
    out = [p for p, trait in (("linux", "p_linux"), ("windows", "p_windows"), ("mac", "p_osx"), ("android", "p_android"))
           if trait in t]
    return out


def game_info(g: dict) -> dict:
    user = g.get("user") if isinstance(g.get("user"), dict) else {}
    return {
        "id": int(g.get("id") or 0),
        "title": str(g.get("title") or "Untitled"),
        "short": str(g.get("short_text") or ""),
        "url": str(g.get("url") or ""),
        "cover": str(g.get("cover_url") or ""),
        "still": str(g.get("still_cover_url") or g.get("cover_url") or ""),
        "classification": str(g.get("classification") or ""),
        "type": str(g.get("type") or ""),
        "author": str(user.get("display_name") or user.get("username") or ""),
        "platforms": platforms(g),
    }


def upload_info(u: dict) -> dict:
    t = _traits(u)
    targets = u.get("launch_targets")
    return {
        "id": int(u.get("id") or 0),
        "filename": str(u.get("filename") or ""),
        "name": str(u.get("display_name") or u.get("filename") or f"Upload {u.get('id')}"),
        "size": int(u.get("size") or 0),
        "storage": str(u.get("storage") or ""),
        "type": str(u.get("type") or ""),
        "build_id": int(u.get("build_id") or 0),
        "version": str((u.get("build") or {}).get("user_version") or "") if isinstance(u.get("build"), dict) else "",
        "channel": str(u.get("channel_name") or ""),
        "updated": str(u.get("updated_at") or ""),
        "platforms": platforms(u),
        "demo": "demo" in t or bool(u.get("demo")),
        "preorder": "preorder" in t or bool(u.get("preorder")),
        "targets": targets if isinstance(targets, list) else [],
    }


def installable(u: dict) -> bool:
    """Something this plugin can put on a Linux handheld: a Linux or Windows build, hosted on itch."""
    return (u["type"] in PLAYABLE_TYPES and u["storage"] in ("hosted", "build")
            and not u["preorder"] and ("linux" in u["platforms"] or "windows" in u["platforms"]))


def pick_upload(uploads: list, prefer: str = "linux") -> dict | None:
    """Best build for this device. Native Linux first unless the user prefers Windows builds;
    full games over demos; wharf builds (versioned, butler) over plain files; then 64-bit-ish
    names; then the newest."""
    ok = [u for u in uploads if installable(u)]
    if not ok:
        return None

    def score(u: dict):
        native = "linux" in u["platforms"]
        plat = (native if prefer != "windows" else "windows" in u["platforms"])
        name = (u["filename"] + " " + u["name"]).lower()
        arch = 0 if any(x in name for x in ("32bit", "32-bit", "x86.", "i386", "win32")) else 1
        arm = 0 if any(x in name for x in ("arm64", "aarch64", "armhf", "raspberry")) else 1
        return (plat, arm, not u["demo"], u["storage"] == "build", arch, u["updated"])
    return sorted(ok, key=score, reverse=True)[0]


def fingerprint(u: dict) -> str:
    """What changes when the developer ships a new version of an upload."""
    if u.get("build_id"):
        return f"b{u['build_id']}"
    return f"f{u.get('filename', '')}:{u.get('size', 0)}"


# ------------------------------------------------------------------ endpoints

def profile(key: str) -> dict:
    u = get("/profile", key).get("user") or {}
    return {"id": int(u.get("id") or 0), "username": str(u.get("username") or ""),
            "name": str(u.get("display_name") or u.get("username") or ""), "cover": str(u.get("cover_url") or "")}


def owned(key: str) -> list:
    """Every game the account owns or has claimed, one entry per game (newest first)."""
    seen: dict = {}
    for page in range(1, MAX_PAGES + 1):
        d = get("/profile/owned-keys", key, {"page": page, "per_page": PER_PAGE})
        keys = d.get("owned_keys") or []
        for k in keys:
            g = k.get("game") if isinstance(k, dict) else None
            if not isinstance(g, dict) or not g.get("id"):
                continue
            gid = int(g["id"])
            if gid in seen:
                continue
            info = game_info(g)
            info["key"] = int(k.get("id") or 0)
            info["added"] = str(k.get("created_at") or "")
            seen[gid] = info
        per = int(d.get("per_page") or PER_PAGE)
        if len(keys) < per:
            break
    return list(seen.values())


def game_detail(key: str, game_id: int) -> dict:
    """A game anyone can see, owned or not, with its price (cents) for the store view."""
    g = get(f"/games/{int(game_id)}", key).get("game") or {}
    if not g.get("id"):
        raise ApiError("itch.io doesn't have that game", 404)
    info = game_info(g)
    info["min_price"] = int(g.get("min_price") or 0)
    info["can_buy"] = "can_be_bought" in _traits(g) or bool(g.get("can_be_bought"))
    return info


def uploads(key: str, game_id: int, download_key: int) -> list:
    d = get(f"/games/{int(game_id)}/uploads", key, {"download_key_id": int(download_key or 0)})
    return [upload_info(u) for u in d.get("uploads") or [] if isinstance(u, dict)]


def open_download(key: str, upload_id: int, download_key: int, timeout: float = 30):
    """Opens the upload's file for streaming. Returns the urllib response (caller closes it).

    /uploads/:id/download answers with a redirect to a signed CDN URL; that hop is made without
    the API key. Some answers are JSON {"url": ...} instead, which is handled the same way."""
    if not key:
        raise ApiError("Not signed in", 401)
    url = _api_url(f"/uploads/{int(upload_id)}/download", {"download_key_id": int(download_key or 0)})
    req = urllib.request.Request(url, headers=_headers(key))
    try:
        r = _opener(False).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location", "")
            e.close()
            return _open_cdn(urllib.parse.urljoin(url, loc), timeout)
        raise ApiError(_message(e.read(4096), e.code), e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach itch.io ({getattr(e, 'reason', e)})") from None
    ctype = r.headers.get("Content-Type", "")
    if "json" in ctype:
        body = r.read(MAX_JSON)
        r.close()
        try:
            d = json.loads(body.decode("utf-8"))
        except ValueError:
            raise ApiError("itch.io sent a broken download answer") from None
        if d.get("errors"):
            raise ApiError("; ".join(str(e) for e in d["errors"][:3]))
        if not d.get("url"):
            raise ApiError("itch.io didn't give a download link")
        return _open_cdn(str(d["url"]), timeout)
    return r


def _open_cdn(url: str, timeout: float):
    if not _https(url):
        raise ApiError("itch.io sent a download link that isn't HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return _opener(True).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise ApiError(f"Download server answered HTTP {e.code}", e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach the download server ({getattr(e, 'reason', e)})") from None


def cover(url: str) -> tuple:
    """(bytes, ext) of a cover image, for the Steam artwork the frontend composes."""
    if not _https(url):
        raise ApiError("No cover image")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with _opener(True).open(req, timeout=20) as r:
            data = r.read(MAX_COVER + 1)
    except urllib.error.HTTPError as e:
        raise ApiError(f"Cover answered HTTP {e.code}", e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach the cover image ({getattr(e, 'reason', e)})") from None
    if len(data) > MAX_COVER:
        raise ApiError("Cover image is too large")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return data, "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "webp"
    raise ApiError("Cover isn't an image Steam can use")
