"""Discovering new games: itch.io's public browse feeds and the official search API.

Browse uses the RSS feed itch.io offers for every browse page (append ".xml" to the page's URL,
https://itch.io/updates/rss-feeds-for-browsing-games), so the filters are itch.io's own:
sort, price, genre, input method (controller support) and platform. Search uses api.itch.io's
/search/games. A feed item only has the game's page URL; its id comes from the page's public
data.json when the game is opened. Fetched only when the Browse tab asks; answers are cached
in memory for a few minutes.
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import api

SITE = "https://itch.io"
MAX_FEED = 4_000_000
CACHE_TTL = 300
_cache: dict = {}

SORTS = ("", "new-and-popular", "top-sellers", "top-rated", "newest")
PRICES = ("", "free", "on-sale", "5-dollars-or-less", "15-dollars-or-less")
GENRES = ("", "action", "adventure", "card-game", "educational", "fighting", "interactive-fiction", "platformer",
          "puzzle", "racing", "rhythm", "role-playing", "shooter", "simulation", "sports", "strategy", "survival",
          "visual-novel", "other")
INPUTS = ("", "gamepad", "x360")          # gamepad = "Gamepad (any)", x360 = "Xbox controller"
PLATFORMS = ("", "linux", "windows")


class BrowseError(api.ApiError):
    pass


def feed_url(sort: str = "", price: str = "", genre: str = "", controller: str = "gamepad",
             platform: str = "", page: int = 1) -> str:
    """https://itch.io/games/<sort>/<facets...>.xml?page=N with only known values."""
    parts = []
    if sort in SORTS and sort:
        parts.append(sort)
    facets = []
    if price in PRICES and price:
        facets.append(price)
    if genre in GENRES and genre:
        facets.append(f"genre-{genre}")
    if controller in INPUTS and controller:
        facets.append(f"input-{controller}")
    if platform in PLATFORMS and platform:
        facets.append(f"platform-{platform}")
    parts += sorted(facets)   # itch.io lists facets alphabetically in its own URLs
    path = "/games" + "".join(f"/{p}" for p in parts) + ".xml"
    q = f"?page={int(page)}" if int(page) > 1 else ""
    return SITE + path + q


def _get(url: str, max_bytes: int, timeout: float = 20) -> bytes:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not (u.hostname == "itch.io" or (u.hostname or "").endswith(".itch.io")):
        raise BrowseError("Refusing a URL outside itch.io")
    req = urllib.request.Request(url, headers={"User-Agent": api.UA, "Accept": "application/rss+xml, application/json, */*"})
    try:
        with api._opener(True).open(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
    except urllib.error.HTTPError as e:
        raise BrowseError(f"itch.io answered HTTP {e.code}", e.code) from None
    except urllib.error.URLError as e:
        raise BrowseError(f"Can't reach itch.io ({getattr(e, 'reason', e)})") from None
    except TimeoutError:
        raise BrowseError("itch.io didn't answer in time") from None
    if len(data) > max_bytes:
        raise BrowseError("itch.io sent an unexpectedly large answer")
    return data


_BRACKET = re.compile(r"\s*\[([^\]]{1,40})\]")
_IMG = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
PLATFORM_WORDS = {"windows": "windows", "linux": "linux", "osx": "mac", "macos": "mac", "mac": "mac", "android": "android"}


def _price(text: str) -> tuple:
    """('$4.99', False) / ('Free', True) from whatever price text the feed carries."""
    t = (text or "").strip()
    if not t:
        return "", None
    if t.lower() in ("free", "0", "$0", "$0.00", "0.00") or re.fullmatch(r"\D{0,3}0+(?:[.,]0+)?\D{0,3}", t):
        return "Free", True
    return t, False


_ITEM = re.compile(r"<item\b[^>]*>(.*?)</item>", re.S | re.I)
_CHILD = re.compile(r"<([A-Za-z][\w:.-]*)\b[^>]*?(?:/>|>(.*?)</\1\s*>)", re.S)


def _text(raw: str | None) -> str:
    """Element text: CDATA unwrapped, entities decoded."""
    if not raw:
        return ""
    raw = raw.strip()
    m = re.fullmatch(r"<!\[CDATA\[(.*?)\]\]>", raw, re.S)
    return (m.group(1) if m else html.unescape(raw)).strip()


def parse_feed(data: bytes) -> list:
    """Items of an itch.io browse feed: [{title, url, cover, price, free, platforms, author, sale}].

    A small regex reader rather than xml.etree: Decky's bundled Python doesn't ship the xml
    package, and these feeds are flat (one level of children, plus <platforms>)."""
    text = data.decode("utf-8", "replace")
    if "<rss" not in text[:2000] and "<channel" not in text[:4000]:
        raise BrowseError("itch.io sent a feed that couldn't be read")
    out = []
    for body in _ITEM.findall(text):
        f: dict = {}
        plats: list = []
        for tag, inner in _CHILD.findall(body):
            name = tag.rsplit(":", 1)[-1].lower()
            if name == "platforms":
                for ptag, pv in _CHILD.findall(inner or ""):
                    key = PLATFORM_WORDS.get(ptag.lower())
                    v = _text(pv).lower()
                    if key and v not in ("no", "false", "0") and key not in plats:
                        plats.append(key)
            elif name not in f:
                f[name] = _text(inner)
        link = f.get("link", "")
        if not link.startswith("https://"):
            continue
        raw_title = f.get("title", "")
        tags = [t.strip() for t in _BRACKET.findall(raw_title)]
        title = f.get("plaintitle") or _BRACKET.sub("", raw_title).strip() or "Untitled"
        if not plats:
            for t in tags:
                key = PLATFORM_WORDS.get(t.lower())
                if key and key not in plats:
                    plats.append(key)
        price_text = f.get("price", "")
        if not price_text:
            price_text = next((t for t in tags if t.lower() == "free" or re.match(r"^\D?\d", t)), "")
        price, free = _price(price_text)
        cover = f.get("imageurl", "")
        if not cover:
            m = _IMG.search(f.get("description", ""))
            cover = m.group(1) if m else ""
        host = urllib.parse.urlparse(link).hostname or ""
        author = host[: -len(".itch.io")] if host.endswith(".itch.io") else ""
        out.append({"title": title, "url": link, "cover": cover if cover.startswith("https://") else "",
                    "price": price, "free": free, "platforms": plats, "author": author,
                    "sale": f.get("salerate", "") or ""})
    return out


def browse(sort="", price="", genre="", controller="gamepad", platform="", page=1) -> dict:
    url = feed_url(sort, price, genre, controller, platform, page)
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    items = parse_feed(_get(url, MAX_FEED))
    # Web-only games can't be installed: keep what has a Linux/Windows build, or unknown platforms.
    shown = [i for i in items if not i["platforms"] or "linux" in i["platforms"] or "windows" in i["platforms"]]
    res = {"items": shown, "page": int(page), "more": len(items) >= 20, "source": url}
    _cache[url] = (time.time(), res)
    if len(_cache) > 40:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:10]:
            _cache.pop(k, None)
    return res


def resolve(url: str) -> int:
    """Game id for a game page URL, from the page's public data.json."""
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not (u.hostname or "").endswith(".itch.io") or not u.path.strip("/"):
        raise BrowseError("Not an itch.io game page")
    path = u.path.rstrip("/")
    d = json.loads(_get(f"https://{u.hostname}{path}/data.json", 200_000).decode("utf-8", "replace") or "{}")
    gid = d.get("id") if isinstance(d, dict) else None
    if not isinstance(gid, int) or gid <= 0:
        raise BrowseError("itch.io didn't say which game that is")
    return gid


def search(key: str, query: str, page: int = 1) -> dict:
    query = (query or "").strip()[:100]
    if not query:
        return {"items": [], "page": 1, "more": False}
    d = api.get("/search/games", key, {"query": query, "page": int(page) if int(page) > 1 else 0})
    games = [g for g in d.get("games") or [] if isinstance(g, dict)]
    items = []
    for g in games:
        info = api.game_info(g)
        if info["type"] == "html" or (info["platforms"] and not {"linux", "windows"} & set(info["platforms"])):
            continue   # web-only or Mac/Android-only: nothing to install here
        mp = int(g.get("min_price") or 0)
        items.append({**info, "price": "Free" if mp == 0 else f"${mp / 100:.2f}", "free": mp == 0, "min_price": mp,
                      "sale": ""})
    per = int(d.get("per_page") or 20)
    return {"items": items, "page": int(page), "more": len(games) >= per}
