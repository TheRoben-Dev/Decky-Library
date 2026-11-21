"""Latest upstream builds we can install, from GitHub releases.

GE-Proton:      GloriousEggroll/proton-ge-custom, asset GE-ProtonX-Y.tar.gz
                plus GE-ProtonX-Y.sha512sum.
Proton-CachyOS: CachyOS/proton-cachyos, assets per CPU level. We pick the
                plain x86_64 build: the maintainer's release notes recommend
                it over _v3/_v4 ("be conservative and use x86_64").
"""
import re
import time

from . import net

SOURCES = {
    "ge": {"repo": "GloriousEggroll/proton-ge-custom", "label": "GE-Proton"},
    "cachyos": {"repo": "CachyOS/proton-cachyos", "label": "Proton-CachyOS"},
}

_cache: dict = {}
TTL = 3600


def _pick_asset(family: str, assets: list):
    names = {a["name"]: a for a in assets}
    tar = None
    if family == "ge":
        tar = next((a for a in assets if a["name"].endswith(".tar.gz")), None)
    elif family == "cachyos":
        cands = [a for a in assets if re.search(r"\.tar\.(xz|gz|zst)$", a["name"])
                 and "arm64" not in a["name"] and "aarch64" not in a["name"]]
        tar = (next((a for a in cands if re.search(r"x86_64\.tar\.", a["name"])), None)
               or next((a for a in cands if "x86_64_v3" in a["name"]), None)
               or next((a for a in cands if "x86_64_v4" not in a["name"]), None))
    if not tar:
        return None
    base = re.sub(r"\.tar\.(xz|gz|zst)$", "", tar["name"])
    sha = names.get(base + ".sha512sum") or names.get(tar["name"] + ".sha512sum")
    return {
        "file": tar["name"],
        "url": tar["browser_download_url"],
        "size": tar.get("size", 0),
        "sha512_url": sha["browser_download_url"] if sha else None,
    }


def latest(family: str, force: bool = False) -> dict:
    src = SOURCES[family]
    hit = _cache.get(family)
    if hit and not force and time.time() - hit["at"] < TTL:
        return hit["data"]
    rel = net.get_json(f"https://api.github.com/repos/{src['repo']}/releases/latest")
    asset = _pick_asset(family, rel.get("assets", []))
    data = {
        "family": family,
        "label": src["label"],
        "tag": rel.get("tag_name", ""),
        "published": rel.get("published_at", ""),
        "asset": asset,
    }
    _cache[family] = {"at": time.time(), "data": data}
    return data
