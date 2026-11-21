"""GOG.com client: sign-in, library, store catalog, product details and artwork.

Uses the same public endpoints as GOG Galaxy and the open-source GOG launchers (Heroic/gogdl,
Lutris, Minigalaxy). The sign-in is GOG's own OAuth page with the Galaxy client id; the tokens it
returns stay in the plugin's settings and are only sent to *.gog.com over HTTPS. Nothing here runs
unless the plugin asks for it: there is no background polling. Certificate checks are never off.
"""
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

AUTH = "https://auth.gog.com"
EMBED = "https://embed.gog.com"
API = "https://api.gog.com"
CONTENT = "https://content-system.gog.com"
CDN = "https://gog-cdn-fastly.gog.com"
CATALOG = "https://catalog.gog.com/v1/catalog"
GAMESDB = "https://gamesdb.gog.com/platforms/gog/external_releases"

# GOG Galaxy's public client (what every open-source GOG launcher signs in with).
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT = "https://embed.gog.com/on_login_success?origin=client"
LOGIN_URL = f"{AUTH}/auth?" + urllib.parse.urlencode(
    {"client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code", "layout": "client2"})

UA = "gog-library-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"
MAX_JSON = 64_000_000        # depot manifests of big games are large
MAX_IMAGE = 12 * 1024 * 1024
MAX_PAGES = 200

_CA_FILES = ("/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")
_ctx = None


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


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context()))


def is_https(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" and bool(u.hostname)


def gog_host(url: str) -> bool:
    """Only GOG's own hosts ever get the access token."""
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return is_https(url) and (h == "gog.com" or h.endswith(".gog.com"))


def _message(status: int, what: str = "GOG") -> str:
    if status in (401, 403):
        return f"{what} refused the request (sign in again if this keeps happening)"
    if status == 404:
        return f"{what} doesn't have that"
    if status == 429:
        return f"{what} asked us to slow down; try again in a minute"
    return f"{what} answered HTTP {status}"


def open_url(url: str, token: str = "", headers: dict | None = None, timeout: float = 30):
    if not is_https(url):
        raise ApiError("Refusing a link that isn't HTTPS")
    h = {"User-Agent": UA, "Accept-Language": "en-US"}
    if token and gog_host(url):
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        return _opener().open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        e.close()
        raise ApiError(_message(e.code), e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach GOG ({getattr(e, 'reason', e)})") from None
    except TimeoutError:
        raise ApiError("GOG didn't answer in time") from None


def get_bytes(url: str, token: str = "", limit: int = MAX_JSON, timeout: float = 30) -> bytes:
    with open_url(url, token, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ApiError("GOG sent more data than expected")
    return data


def get_json(url: str, token: str = "", timeout: float = 30):
    data = get_bytes(url, token, timeout=timeout)
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise ApiError("GOG sent an answer that isn't JSON") from None


def get_zjson(url: str, token: str = ""):
    """Galaxy manifests are zlib-compressed JSON (sometimes plain JSON)."""
    data = get_bytes(url, token, timeout=60)
    try:
        data = zlib.decompress(data, 15)
    except zlib.error:
        pass
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise ApiError("GOG sent a broken manifest") from None


# ------------------------------------------------------------------ sign-in

CODE_RE = re.compile(r"[A-Za-z0-9_\-.~]{20,}")


def extract_code(text: str) -> str:
    """The code from the address GOG lands on (…on_login_success?origin=client&code=XYZ) or a bare code."""
    text = (text or "").strip()
    m = re.search(r"[?&#]code=([^&#\s]+)", text)
    if m:
        return urllib.parse.unquote(m.group(1))
    text = re.sub(r"\s+", "", text)
    return text if CODE_RE.fullmatch(text) else ""


def _token_request(params: dict) -> dict:
    q = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, **params}
    try:
        d = get_json(f"{AUTH}/token?" + urllib.parse.urlencode(q))
    except ApiError as e:
        if e.status in (400, 401, 403):
            raise ApiError("GOG didn't accept that sign-in. Codes work once and expire after a few minutes: sign in again.", e.status) from None
        raise
    if not d.get("access_token") or not d.get("refresh_token"):
        raise ApiError("GOG didn't return a sign-in token")
    return {"access_token": d["access_token"], "refresh_token": d["refresh_token"],
            "expires": time.time() + int(d.get("expires_in") or 3600), "user_id": str(d.get("user_id") or "")}


def exchange_code(code: str) -> dict:
    return _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT})


def refresh(refresh_token: str) -> dict:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})


class Auth:
    """Holds the tokens and refreshes the access token (valid one hour) when it runs out."""

    def __init__(self, load, save):
        self._load = load      # () -> dict
        self._save = save      # (dict) -> None
        self.lock = threading.Lock()

    def signed_in(self) -> bool:
        return bool(self._load().get("refresh_token"))

    def token(self, force: bool = False) -> str:
        with self.lock:
            t = self._load()
            if not t.get("refresh_token"):
                raise ApiError("Not signed in", 401)
            if force or not t.get("access_token") or time.time() > float(t.get("expires", 0)) - 120:
                try:
                    nt = refresh(t["refresh_token"])
                except ApiError as e:
                    if e.status in (400, 401, 403):
                        raise ApiError("Your GOG sign-in expired. Sign in again.", 401) from None
                    raise
                t = {**t, **nt}
                self._save(t)
            return t["access_token"]


def user_data(token: str) -> dict:
    d = get_json(f"{EMBED}/userData.json", token)
    if not d.get("isLoggedIn", True):
        raise ApiError("GOG says you're not signed in", 401)
    return {"id": str(d.get("galaxyUserId") or d.get("userId") or ""), "username": d.get("username") or "",
            "avatar": (d.get("avatars") or {}).get("medium") or ""}


# ------------------------------------------------------------------ library

def _img(path: str, suffix: str) -> str:
    """GOG images come as protocol-relative hashes (//images-1.gog-statics.com/<hash>)."""
    if not path:
        return ""
    if path.startswith("//"):
        path = "https:" + path
    if re.search(r"\.(jpg|jpeg|png|webp)$", path):
        return path
    return path + suffix


def platforms_of(works: dict) -> list:
    out = []
    for k, name in (("Linux", "linux"), ("Windows", "windows"), ("Mac", "mac")):
        if (works or {}).get(k):
            out.append(name)
    return out


def library(token: str) -> list:
    """Owned games (embed getFilteredProducts, 100 per page)."""
    games = []
    page = 1
    while page <= MAX_PAGES:
        d = get_json(f"{EMBED}/account/getFilteredProducts?mediaType=1&sortBy=date_purchased&page={page}", token)
        for p in d.get("products") or []:
            if not isinstance(p, dict) or not p.get("id"):
                continue
            url = p.get("url") or ""
            games.append({
                "id": int(p["id"]), "title": str(p.get("title") or ""),
                "cover": _img(p.get("image") or "", "_392.jpg"),
                "image": _img(p.get("image") or "", ".jpg"),
                "url": ("https://www.gog.com" + url) if url.startswith("/") else url,
                "platforms": platforms_of(p.get("worksOn") or {}),
                "category": str(p.get("category") or ""),
                "hidden": bool(p.get("isHidden")),
            })
        total = int(d.get("totalPages") or 1)
        if page >= total:
            break
        page += 1
    return games


def owned_ids(token: str) -> list:
    d = get_json(f"{EMBED}/user/data/games", token)
    return [int(x) for x in d.get("owned") or [] if str(x).isdigit()]


def product(game_id: int, token: str = "") -> dict:
    """api.gog.com/products/<id> with downloads, description and DLCs."""
    d = get_json(f"{API}/products/{int(game_id)}?expand=downloads,description,expanded_dlcs&locale=en-US", token)
    imgs = d.get("images") or {}
    desc = d.get("description") or {}
    lead = re.sub(r"<[^>]+>", " ", str(desc.get("lead") or desc.get("full") or ""))
    lead = re.sub(r"\s+", " ", lead).strip()[:600]
    compat = dict(d.get("content_system_compatibility") or {})
    installers = []
    for i in ((d.get("downloads") or {}).get("installers") or []):
        if not isinstance(i, dict):
            continue
        os_ = i.get("os")
        if os_ in ("windows", "linux", "mac", "osx"):
            compat[os_ if os_ != "mac" else "osx"] = True
        installers.append({
            "id": str(i.get("id") or ""), "os": "mac" if os_ == "osx" else str(os_ or ""),
            "language": str(i.get("language") or ""), "version": str(i.get("version") or ""),
            "size": int(i.get("total_size") or 0), "name": str(i.get("name") or ""),
            "files": [{"id": str(f.get("id") or ""), "size": int(f.get("size") or 0), "downlink": str(f.get("downlink") or "")}
                      for f in (i.get("files") or []) if isinstance(f, dict)],
        })
    plats = [p for p, k in (("linux", "linux"), ("windows", "windows"), ("mac", "osx")) if compat.get(k)]
    links = d.get("links") or {}
    return {
        "id": int(d.get("id") or game_id), "title": str(d.get("title") or ""), "slug": str(d.get("slug") or ""),
        "url": str(links.get("product_card") or ""), "short": lead,
        "background": _img(imgs.get("background") or "", ""), "logo": _img(imgs.get("logo2x") or imgs.get("logo") or "", ""),
        "platforms": plats, "installers": installers, "game_type": str(d.get("game_type") or ""),
        "preorder": bool(d.get("is_pre_order")),
        "dlcs": [{"id": int(x.get("id")), "title": str(x.get("title") or ""), "installers": [
            {"os": "mac" if j.get("os") == "osx" else str(j.get("os") or ""), "language": str(j.get("language") or ""),
             "version": str(j.get("version") or ""), "size": int(j.get("total_size") or 0),
             "files": [{"size": int(f.get("size") or 0), "downlink": str(f.get("downlink") or "")} for f in (j.get("files") or [])]}
            for j in ((x.get("downloads") or {}).get("installers") or []) if isinstance(j, dict)]}
            for x in (d.get("expanded_dlcs") or []) if isinstance(x, dict) and x.get("id")],
    }


def pick_installer(installers: list, os_: str, lang: str = "en") -> dict | None:
    cands = [i for i in installers if i.get("os") == os_ and i.get("files")]
    if not cands:
        return None
    short = (lang or "en").split("-")[0].lower()
    for want in (short, "en"):
        for i in cands:
            if i.get("language", "").lower() == want:
                return i
    return cands[0]


def downlink(url: str, token: str) -> str:
    """An installer file's downlink (api.gog.com/products/<id>/downlink/...) -> real CDN URL."""
    if not gog_host(url):
        raise ApiError("Unexpected download link")
    d = get_json(url, token)
    link = str(d.get("downlink") or "")
    if not is_https(link):
        raise ApiError("GOG didn't give a download link")
    return link


# ------------------------------------------------------------------ content system (Galaxy builds)

def builds(game_id: int, os_: str, token: str) -> list:
    """Galaxy builds for 'windows' or 'osx' (Linux games only come as installers)."""
    try:
        d = get_json(f"{CONTENT}/products/{int(game_id)}/os/{os_}/builds?generation=2", token)
    except ApiError as e:
        if e.status in (404, 400):
            return []
        raise
    return [b for b in d.get("items") or [] if isinstance(b, dict) and b.get("link")]


def pick_build(items: list) -> dict | None:
    """The default public branch (branch null), newest first as GOG lists them."""
    for b in items:
        if b.get("branch") in (None, "") and b.get("public", True):
            return b
    return items[0] if items else None


def galaxy_path(h: str) -> str:
    return h if "/" in h else f"{h[0:2]}/{h[2:4]}/{h}"


def secure_link(game_id, token: str, generation: int = 2, path: str = "/") -> list:
    if generation == 2:
        q = f"_version=2&generation=2&path={urllib.parse.quote(path)}"
    else:
        q = f"_version=2&type=depot&path={urllib.parse.quote(path)}"
    d = get_json(f"{CONTENT}/products/{game_id}/secure_link?{q}", token)
    urls = d.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ApiError("GOG didn't give download servers")
    return urls


def endpoint_url(endpoint: dict, extra_path: str) -> str:
    params = dict(endpoint.get("parameters") or {})
    fmt = endpoint.get("url_format")
    if fmt:
        params["path"] = str(params.get("path", "")) + extra_path
        url = str(fmt)
        for k, v in params.items():
            url = url.replace("{" + k + "}", str(v))
        return url
    return str(endpoint.get("url", "")) + extra_path


# ------------------------------------------------------------------ store catalog

SORTS = {"trending": "desc:trending", "bestselling": "desc:bestselling", "newest": "desc:releaseDate",
         "rating": "desc:reviewsRating", "discount": "desc:discount", "title": "asc:title"}
PRICES = {"free": ("price", "between:0,0"), "under10": ("price", "between:0,10"),
          "under25": ("price", "between:0,25"), "sale": ("discounted", "eq:true")}
GENRES = ("action", "adventure", "racing", "rpg", "shooter", "simulation", "sports", "strategy")
SYSTEMS = {"": "linux,windows", "linux": "linux", "windows": "windows"}
PER_PAGE = 48


def _price(p: dict) -> tuple:
    p = p or {}
    final = str(p.get("final") or "")
    try:
        amount = float((p.get("finalMoney") or {}).get("amount"))
    except (TypeError, ValueError):
        amount = None
    free = amount == 0 or final.lower() in ("free", "$0.00", "0")
    disc = str(p.get("discount") or "").strip()
    return final, free, (disc if disc and disc not in ("0%", "-0%") else ""), amount


def catalog_item(p: dict) -> dict:
    final, free, disc, amount = _price(p.get("price") or {})
    feats = [f.get("slug") for f in p.get("features") or [] if isinstance(f, dict)]
    oses = [("mac" if o == "osx" else o) for o in p.get("operatingSystems") or [] if isinstance(o, str)]
    try:
        gid = int(p.get("id"))
    except (TypeError, ValueError):
        gid = 0
    return {
        "id": gid, "title": str(p.get("title") or ""), "slug": str(p.get("slug") or ""),
        "url": str(p.get("storeLink") or (f"https://www.gog.com/en/game/{p.get('slug')}" if p.get("slug") else "")),
        "cover": str(p.get("coverHorizontal") or ""), "vertical": str(p.get("coverVertical") or ""),
        "price": final, "free": free, "amount": amount, "sale": disc, "platforms": oses,
        "controller": "controller_support" in feats, "type": str(p.get("productType") or ""),
        "developer": ", ".join(str(x) for x in (p.get("developers") or [])[:2]),
        "state": str(p.get("productState") or ""),
    }


def catalog(sort: str = "", price: str = "", genre: str = "", controller: str = "controller",
            platform: str = "", query: str = "", page: int = 1, country: str = "US", currency: str = "USD") -> dict:
    q = {"limit": PER_PAGE, "page": max(1, int(page)), "order": SORTS.get(sort, SORTS["trending"]),
         "productType": "in:game,pack", "countryCode": country, "locale": "en-US", "currencyCode": currency}
    q["systems"] = f"in:{SYSTEMS.get(platform, SYSTEMS[''])}"
    if query:
        q["query"] = f"like:{query[:100]}"
        if sort == "":
            q.pop("order")   # relevance
    if price in PRICES:
        k, v = PRICES[price]
        q[k] = v
    if genre in GENRES:
        q["genres"] = f"in:{genre}"
    if controller == "controller":
        q["features"] = "in:controller_support"
    d = get_json(CATALOG + "?" + urllib.parse.urlencode(q, safe=":,"), timeout=20)
    items = [catalog_item(p) for p in d.get("products") or [] if isinstance(p, dict)]
    pages = int(d.get("pages") or 0)
    return {"items": [i for i in items if i["id"]], "page": q["page"], "more": q["page"] < pages,
            "total": int(d.get("productCount") or 0)}


# ------------------------------------------------------------------ artwork

def gamesdb_art(game_id: int) -> dict:
    """Official artwork URLs from GOG's games database: vertical cover, hero, logo, wide, icon."""
    try:
        d = get_json(f"{GAMESDB}/{int(game_id)}", timeout=15)
    except ApiError:
        return {}
    g = d.get("game") or {}

    def u(key: str, ext: str) -> str:
        fmt = ((g.get(key) or {}).get("url_format") or "") if isinstance(g.get(key), dict) else ""
        return fmt.replace("{formatter}", "").replace("{ext}", ext) if fmt else ""
    return {"capsule": u("vertical_cover", "jpg"), "hero": u("background", "jpg"), "logo": u("logo", "png"),
            "wide": u("horizontal_artwork", "jpg") or u("cover", "jpg"),
            "icon": u("square_icon", "png") or u("icon", "png")}


def image(url: str) -> tuple:
    """(bytes, ext) of an image for Steam's artwork (fetched here so the canvas isn't tainted)."""
    if not is_https(url):
        raise ApiError("No image")
    data = get_bytes(url, limit=MAX_IMAGE, timeout=25)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "webp"
    raise ApiError("Not an image Steam can use")
