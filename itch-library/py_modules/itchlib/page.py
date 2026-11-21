"""A game's public itch.io page as store details: description, screenshots, info panel, rating.

itch.io's API has no description or screenshots, so these come from the game's own page, fetched
once when its detail page opens and cached (memory + disk) for a day. Parsed with small regexes
(Decky's bundled Python has no html.parser), and reduced to plain text and image URLs: no page
HTML ever reaches the UI.
"""
import html
import json
import os
import re
import time
import urllib.parse

from . import browse

TTL = 24 * 3600
MAX_PAGE = 3_000_000
IMG_HOSTS = ("img.itch.zone", "img.itch.io")
_mem: dict = {}

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>", re.S)
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "blockquote", "pre", "tr", "hr", "ul", "ol"}
INFO_KEEP = ("Status", "Platforms", "Release date", "Published", "Updated", "Rating", "Author", "Authors", "Genre",
             "Made with", "Tags", "Average session", "Languages", "Inputs", "Accessibility", "Multiplayer",
             "Player count", "Mentions", "Content")


def _img_ok(u: str) -> bool:
    p = urllib.parse.urlparse(u)
    return p.scheme == "https" and (p.hostname or "") in IMG_HOSTS


def _element(text: str, class_word: str, tag: str = "div") -> str:
    """Inner HTML of the first <tag> whose class list contains class_word (nesting-aware)."""
    m = re.search(rf"<{tag}\b[^>]*\bclass=[\"'][^\"']*\b{re.escape(class_word)}\b[^\"']*[\"'][^>]*>", text, re.I)
    if not m:
        return ""
    depth, pos = 1, m.end()
    pat = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
    for t in pat.finditer(text, pos):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return text[pos:t.start()]
    return text[pos:pos + 200_000]


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t\r\f\v\u00a0]+", " ", s).strip()
    return re.sub(r" ([,.;:)])", r"\1", s)


def description(inner: str, limit: int = 60) -> list:
    """[{t: 'h'|'p'|'li'|'img', text|src}] from description HTML."""
    inner = re.sub(r"<(script|style|iframe|noscript)\b.*?</\1\s*>", " ", inner, flags=re.S | re.I)
    out: list = []
    buf: list = []
    kind = "p"

    def flush():
        nonlocal buf, kind
        t = re.sub(r"\s+", " ", html.unescape("".join(buf))).strip()
        if t:
            out.append({"t": kind, "text": t[:2000]})
        buf, kind = [], "p"

    pos = 0
    for m in _TAG.finditer(inner):
        buf.append(inner[pos:m.start()])
        pos = m.end()
        closing, name = m.group(1) == "/", m.group(2).lower()
        if name == "img" and not closing:
            src = re.search(r"""\bsrc=["']([^"']+)["']""", m.group(0))
            if src and _img_ok(html.unescape(src.group(1))):
                flush()
                out.append({"t": "img", "src": html.unescape(src.group(1))})
        elif name in BLOCK_TAGS:
            flush()
            if not closing and name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                kind = "h"
            elif not closing and name == "li":
                kind = "li"
        if len(out) >= limit:
            break
    buf.append(inner[pos:])
    flush()
    return out[:limit]


def parse(text: str) -> dict:
    desc = description(_element(text, "formatted_description"))
    shots = []
    for href in re.findall(r"""<a\b[^>]*\bhref=["']([^"']+)["']""", _element(text, "screenshot_list"), re.I):
        u = html.unescape(href)
        if _img_ok(u) and u not in shots:
            shots.append(u)
    info = []
    panel = _element(text, "game_info_panel_widget")
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", panel, re.S | re.I):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) >= 2:
            k, v = _clean(cells[0]), _clean(cells[1])
            if k in INFO_KEEP and v:
                info.append([k, v[:400]])
    rating = {}
    rv = re.search(r"""itemprop=["']ratingValue["'][^>]*content=["']([\d.]+)""", text)
    rc = re.search(r"""itemprop=["']ratingCount["'][^>]*content=["'](\d+)""", text)
    if rv:
        rating = {"value": float(rv.group(1)), "count": int(rc.group(1)) if rc else 0}
    video = ""
    vm = re.search(r"""<div\b[^>]*class=["'][^"']*video_embed[^"']*["'][^>]*>.*?<iframe\b[^>]*src=["']([^"']+)""", text, re.S | re.I)
    if vm:
        v = html.unescape(vm.group(1))
        yt = re.search(r"youtube(?:-nocookie)?\.com/embed/([\w-]{6,20})", v)
        if yt:
            video = f"https://www.youtube.com/watch?v={yt.group(1)}"
    return {"description": desc, "screenshots": shots[:20], "info": info, "rating": rating, "video": video}


def store_page(url: str, cache_dir: str = "") -> dict:
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https" or not (u.hostname or "").endswith(".itch.io") or not u.path.strip("/"):
        raise browse.BrowseError("No itch.io page for this game")
    key = f"https://{u.hostname}{u.path.rstrip('/')}"
    hit = _mem.get(key)
    path = os.path.join(cache_dir, re.sub(r"[^a-z0-9]+", "_", key.lower())[-120:] + ".json") if cache_dir else ""
    if not hit and path:
        try:
            with open(path, encoding="utf-8") as f:
                hit = json.load(f)
        except (OSError, ValueError):
            hit = None
    if hit and time.time() - hit.get("at", 0) < TTL:
        return hit["page"]
    try:
        page = parse(browse._get(key, MAX_PAGE).decode("utf-8", "replace"))
    except browse.BrowseError:
        if hit:      # an older copy beats nothing while itch.io is refusing requests
            return {**hit["page"], "stale": True}
        raise
    entry = {"at": time.time(), "page": page}
    _mem[key] = entry
    if len(_mem) > 100:
        _mem.pop(next(iter(_mem)))
    if path:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entry, f)
            os.replace(tmp, path)
            names = os.listdir(cache_dir)
            if len(names) > 300:      # keep the cache small: drop the oldest third
                full = sorted((os.path.join(cache_dir, n) for n in names), key=os.path.getmtime)
                for old in full[:100]:
                    os.unlink(old)
        except OSError:
            pass
    return page
