"""Browse and search the Epic Games Store: the store's public GraphQL endpoint (the one the website
uses, no account needed) and the public free-games feed. Only called when the Browse tab asks.

Filters: sort, price (free / on sale), genre and features are Epic's own catalog tags. Tag ids are
looked up by name from Epic's tag list once a week rather than hardcoded, so "Controller Support"
keeps working if Epic renumbers it.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL = "https://store.epicgames.com/graphql"
FREE_FEED = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale={locale}&country={country}&allowCountries={country}"
STORE_PAGE = "https://store.epicgames.com/{locale}/p/{slug}"
STORE_SEARCH = "https://store.epicgames.com/{locale}/browse?q={q}&sortBy=relevancy&sortDir=DESC&count=40"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TIMEOUT = 20
PAGE = 40
TAGS_TTL = 7 * 24 * 3600
CATEGORY = "games/edition/base|bundles/games|games/edition|editors"

# Shown in the Genre dropdown when Epic's tag list has them (matched by name).
GENRES = ["Action", "Adventure", "Action-Adventure", "Casual", "Fighting", "Horror", "Indie", "Open World",
          "Platformer", "Puzzle", "Racing", "RPG", "Rogue-Lite", "Shooter", "Simulation", "Sports", "Strategy",
          "Survival", "Card Game", "Stealth", "Narration", "Exploration"]
CONTROLLER_NAMES = ("controller support", "full controller support", "controller")

SORTS = {
    "": ("relevancy", "DESC"),
    "new": ("releaseDate", "DESC"),
    "price": ("currentPrice", "ASC"),
    "price-desc": ("currentPrice", "DESC"),
    "title": ("title", "ASC"),
}

SEARCH_QUERY = """query searchStoreQuery($allowCountries: String, $category: String, $count: Int, $country: String!, $keywords: String, $locale: String, $sortBy: String, $sortDir: String, $start: Int, $tag: String, $withPrice: Boolean = true%VARS%) {
  Catalog {
    searchStore(allowCountries: $allowCountries, category: $category, count: $count, country: $country, keywords: $keywords, locale: $locale, sortBy: $sortBy, sortDir: $sortDir, start: $start, tag: $tag%ARGS%) {
      elements {
        title id namespace description effectiveDate
        keyImages { type url }
        seller { name }
        productSlug urlSlug
        tags { id }
        items { id namespace }
        customAttributes { key value }
        categories { path }
        price(country: $country) @include(if: $withPrice) {
          totalPrice { discountPrice originalPrice discount currencyCode currencyInfo { decimals } fmtPrice(locale: $locale) { originalPrice discountPrice } }
        }
      }
      paging { count total }
    }
  }
}"""

TAGS_QUERY = """query catalogTags($namespace: String!) {
  Catalog { tags(namespace: $namespace, start: 0, count: 999) { elements { aliases id name referenceCount status } } }
}"""


class CatalogError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def _request(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json", "Accept-Language": "en-US,en;q=0.8"}
    if data is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    last = None
    # The storefront sometimes answers the first request with an HTML 403; one retry clears it.
    for attempt in range(2):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read(6 * 1024 * 1024)
            return json.loads(raw.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = CatalogError(f"The Epic store answered {e.code}", e.code)
            if e.code not in (403, 429, 502, 503) or attempt:
                break
            time.sleep(1.0)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = CatalogError(f"Couldn't reach the Epic store ({getattr(e, 'reason', e)})")
            break
        except ValueError:
            last = CatalogError("The Epic store sent something unexpected")
            break
    raise last or CatalogError("The Epic store didn't answer")


def _graphql(query: str, variables: dict) -> dict:
    d = _request(GRAPHQL, {"query": query, "variables": variables})
    if d.get("errors") and not d.get("data"):
        msg = (d["errors"][0] or {}).get("message", "query failed") if isinstance(d["errors"], list) else "query failed"
        raise CatalogError(f"Epic store: {msg}")
    return d.get("data") or {}


# ------------------------------------------------------------------ tags

def tags(cache_path: str) -> dict:
    """{"controller": id or "", "genres": [[id, name], ...]} from Epic's tag list, cached a week."""
    try:
        with open(cache_path, encoding="utf-8") as f:
            c = json.load(f)
        if time.time() - float(c.get("at", 0)) < TAGS_TTL and isinstance(c.get("genres"), list):
            return c
    except (OSError, ValueError):
        c = None
    try:
        data = _graphql(TAGS_QUERY, {"namespace": "epic", "locale": "en-US", "country": "US"})
        els = (((data.get("Catalog") or {}).get("tags") or {}).get("elements")) or []
    except CatalogError:
        if c:
            return c        # stale beats nothing
        return {"controller": "", "genres": [], "at": 0}
    by_name = {}
    for t in els:
        if not isinstance(t, dict) or not t.get("id") or not t.get("name"):
            continue
        if t.get("status") and str(t["status"]).upper() not in ("ACTIVE", ""):
            continue
        names = [str(t["name"])] + [str(a) for a in (t.get("aliases") or []) if isinstance(a, str)]
        for n in names:
            key = n.strip().lower()
            # Several tags can share a name; keep the most used one.
            if key not in by_name or int(t.get("referenceCount") or 0) > int(by_name[key].get("referenceCount") or 0):
                by_name[key] = t
    ctrl = next((str(by_name[n]["id"]) for n in CONTROLLER_NAMES if n in by_name), "")
    genres = [[str(by_name[g.lower()]["id"]), g] for g in GENRES if g.lower() in by_name]
    out = {"controller": ctrl, "genres": genres, "at": time.time()}
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ items

IMG_TALL = ("OfferImageTall", "DieselStoreFrontTall", "DieselGameBoxTall", "Thumbnail", "CodeRedemption_340x440")
IMG_WIDE = ("OfferImageWide", "DieselStoreFrontWide", "DieselGameBox", "featuredMedia", "VaultClosed")


def _slug(e: dict) -> str:
    ca = {a.get("key"): a.get("value") for a in e.get("customAttributes") or [] if isinstance(a, dict)}
    for s in (e.get("productSlug"), ca.get("com.epicgames.app.productSlug"), e.get("urlSlug")):
        s = (s or "").strip().strip("/")
        if s and not re.fullmatch(r"[0-9a-f]{32}", s):
            return re.sub(r"/home$", "", s)
    return ""


def item(e: dict, controller_tag: str, locale: str) -> dict | None:
    if not isinstance(e, dict) or not e.get("title"):
        return None
    imgs = {}
    for i in e.get("keyImages") or []:
        if isinstance(i, dict) and i.get("type") and i.get("url"):
            imgs.setdefault(i["type"], i["url"])
    tall = next((imgs[k] for k in IMG_TALL if imgs.get(k)), "")
    wide = next((imgs[k] for k in IMG_WIDE if imgs.get(k)), "")
    tp = ((e.get("price") or {}).get("totalPrice")) or {}
    fmt = tp.get("fmtPrice") or {}
    cur = tp.get("discountPrice")
    orig = tp.get("originalPrice")
    free = None if cur is None else int(cur) == 0
    sale = 0
    if isinstance(cur, int) and isinstance(orig, int) and orig > 0 and cur < orig:
        sale = round((orig - cur) * 100 / orig)
    slug = _slug(e)
    q = urllib.parse.quote(e["title"])
    url = STORE_PAGE.format(locale=locale, slug=slug) if slug else STORE_SEARCH.format(locale=locale, q=q)
    tag_ids = {str(t.get("id")) for t in e.get("tags") or [] if isinstance(t, dict)}
    return {
        "id": str(e.get("id") or ""),
        "ns": str(e.get("namespace") or ""),
        "title": e["title"].strip(),
        "seller": ((e.get("seller") or {}).get("name") or ""),
        "description": (e.get("description") or "").strip()[:500],
        "tall": tall, "wide": wide,
        "url": url,
        "free": free,
        "price": "Free" if free else (fmt.get("discountPrice") or ""),
        "original": fmt.get("originalPrice") or "",
        "sale": sale,
        "controller": bool(controller_tag) and controller_tag in tag_ids,
        "released": (e.get("effectiveDate") or "")[:10],
    }


def _search_query(v: dict) -> tuple:
    """Runs the search with Epic's freeGame/onSale filters; if this store version doesn't know
    those arguments, runs it without them and filters the page here instead."""
    extra = [k for k in ("freeGame", "onSale") if k in v]
    q = SEARCH_QUERY.replace("%VARS%", "".join(f", ${k}: Boolean" for k in extra)) \
                    .replace("%ARGS%", "".join(f", {k}: ${k}" for k in extra))
    try:
        return _graphql(q, v), ""
    except CatalogError as e:
        if not extra or "argument" not in str(e).lower():
            raise
    plain = {k: val for k, val in v.items() if k not in extra}
    q = SEARCH_QUERY.replace("%VARS%", "").replace("%ARGS%", "")
    return _graphql(q, plain), ("free" if "freeGame" in extra else "sale")


def search(opts: dict, cache_dir: str) -> dict:
    """One page of store results. opts: query, sort, price ('', 'free', 'sale'), genre (tag id),
    controller (bool), country, locale, page (1-based)."""
    country = re.sub(r"[^A-Z]", "", str(opts.get("country") or "US").upper())[:2] or "US"
    locale = str(opts.get("locale") or "en-US")
    if not re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", locale):
        locale = "en-US"
    page = max(1, int(opts.get("page") or 1))
    t = tags(os.path.join(cache_dir, "tags.json"))
    tag_ids = []
    controller = bool(opts.get("controller"))
    note = ""
    if controller:
        if t.get("controller"):
            tag_ids.append(t["controller"])
        else:
            note = "Epic didn't send its Controller Support tag, so this shows every game."
    genre = str(opts.get("genre") or "")
    if genre and re.fullmatch(r"\d+", genre):
        tag_ids.append(genre)
    sort_by, sort_dir = SORTS.get(str(opts.get("sort") or ""), SORTS[""])
    v = {
        "allowCountries": country, "country": country, "locale": locale,
        "category": CATEGORY, "count": PAGE, "start": (page - 1) * PAGE,
        "sortBy": sort_by, "sortDir": sort_dir, "withPrice": True,
    }
    query = str(opts.get("query") or "").strip()[:100]
    if query:
        v["keywords"] = query
        if not opts.get("sort"):
            v["sortBy"], v["sortDir"] = "relevancy", "DESC"
    if tag_ids:
        v["tag"] = "|".join(tag_ids)
    price = str(opts.get("price") or "")
    if price == "free":
        v["freeGame"] = True
    elif price == "sale":
        v["onSale"] = True
    data, local_filter = _search_query(v)
    ss = ((data.get("Catalog") or {}).get("searchStore")) or {}
    items = [i for i in (item(e, t.get("controller", ""), locale) for e in ss.get("elements") or []) if i]
    if local_filter == "free":
        items = [i for i in items if i["free"]]
    elif local_filter == "sale":
        items = [i for i in items if i["sale"]]
    total = int(((ss.get("paging") or {}).get("total")) or 0)
    return {"items": items, "page": page, "more": page * PAGE < total, "total": total, "note": note,
            "genres": t.get("genres", []), "controllerTag": bool(t.get("controller"))}


def free_now(country: str, locale: str = "en-US") -> list:
    """Games Epic is giving away right now (claim them on the store page)."""
    country = re.sub(r"[^A-Z]", "", (country or "US").upper())[:2] or "US"
    d = _request(FREE_FEED.format(locale=urllib.parse.quote(locale), country=country))
    els = (((d.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
    out = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    for e in els:
        promos = ((e.get("promotions") or {}).get("promotionalOffers")) or []
        active = None
        for group in promos:
            for p in (group or {}).get("promotionalOffers") or []:
                ds = p.get("discountSetting") or {}
                if ds.get("discountPercentage") == 0 and (p.get("startDate") or "") <= now + "Z" <= (p.get("endDate") or "9"):
                    active = p
        if not active:
            continue
        it = item(e, "", locale)
        if it:
            it["free"] = True
            it["price"] = "Free"
            it["until"] = (active.get("endDate") or "")[:10]
            out.append(it)
    return out
