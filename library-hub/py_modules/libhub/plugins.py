"""Decky plugins: what's installed, what a release zip contains, and dependencies.

Installing and uninstalling plugins is done by Decky Loader itself (frontend calls
utilities/install_plugin and utilities/uninstall_plugin), so Decky shows its own confirmation,
checks the SHA-256 again, places the folder and reloads the plugin. This module only answers
questions and validates zips before they're handed over.
"""
import io
import json
import os
import re
import stat
import zipfile

from . import net

MAX_UNPACKED = 120 * 1024 * 1024
MAX_ENTRIES = 5000

STORE_URL = "https://plugins.deckbrew.xyz/plugins"
STORE_CDN = "https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/"
CSS_LOADER = "CSS Loader"

# What each item needs to be useful. "decky" = a plugin from Decky's store, "steam" = a Steam app.
DEPENDENCIES = {
    "nightgrid-theme": [{"kind": "decky", "name": CSS_LOADER}],
    "vex-performance": [{"kind": "steam", "appid": 993090, "name": "Lossless Scaling",
                         "why": "needed for frame generation"}],
}


def installed(plugins_root: str) -> dict:
    """{plugin.json name: package.json version or None} for every folder in ~/homebrew/plugins."""
    out = {}
    try:
        entries = os.listdir(plugins_root)
    except OSError:
        return out
    for d in entries:
        p = os.path.join(plugins_root, d)
        try:
            with open(os.path.join(p, "plugin.json"), encoding="utf-8") as f:
                name = json.load(f).get("name")
        except (OSError, ValueError):
            continue
        if not name:
            continue
        ver = None
        try:
            with open(os.path.join(p, "package.json"), encoding="utf-8") as f:
                ver = json.load(f).get("version")
        except (OSError, ValueError):
            pass
        out[name] = ver
    return out


def inspect_zip(data: bytes) -> dict:
    """Checks a plugin zip the way Decky will unpack it (one top-level folder with plugin.json
    and main.py, no absolute paths, `..`, links or oversized content); returns name + version."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if not infos or len(infos) > MAX_ENTRIES:
        raise ValueError("zip is empty or has too many entries")
    tops, total = set(), 0
    for i in infos:
        name = i.filename
        parts = name.split("/")
        if name.startswith("/") or "\\" in name or ":" in parts[0] or ".." in parts or not parts[0]:
            raise ValueError(f"unexpected path in zip: {name}")
        mode = i.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise ValueError(f"link in zip: {name}")
        tops.add(parts[0])
        total += i.file_size
        if total > MAX_UNPACKED:
            raise ValueError("zip unpacks too large")
    if len(tops) != 1:
        raise ValueError("zip must contain exactly one plugin folder")
    top = tops.pop()
    try:
        meta = json.loads(zf.read(f"{top}/plugin.json").decode("utf-8"))
        zf.getinfo(f"{top}/main.py")
    except KeyError:
        raise ValueError("zip has no plugin.json / main.py")
    try:
        version = json.loads(zf.read(f"{top}/package.json").decode("utf-8")).get("version")
    except KeyError:
        version = None
    name = meta.get("name")
    if not name or name != top:
        raise ValueError("plugin.json name doesn't match the zip's folder")
    return {"name": name, "version": version}


def store_artifact(store: list, name: str):
    """Newest version of `name` in Decky's store index → {artifact, hash, version}."""
    for p in store or []:
        if p.get("name") != name:
            continue
        for v in p.get("versions") or []:
            h = (v.get("hash") or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", h):
                continue
            art = v.get("artifact") or STORE_CDN + h + ".zip"
            if not art.startswith("https://"):
                continue
            return {"artifact": art, "hash": h, "version": v.get("name") or "", "name": name}
    return None


def fetch_store_artifact(name: str):
    return store_artifact(net.get_json(STORE_URL, hosts=net.STORE_HOSTS, max_bytes=8_000_000), name)


def steam_app_installed(user_home: str, appid: int) -> bool:
    """Looks for appmanifest_<appid>.acf in every Steam library listed in libraryfolders.vdf."""
    roots = [os.path.join(user_home, ".local", "share", "Steam"), os.path.join(user_home, ".steam", "steam")]
    libs = set()
    for r in roots:
        libs.add(os.path.join(r, "steamapps"))
        try:
            with open(os.path.join(r, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
                for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                    libs.add(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps"))
        except OSError:
            pass
    return any(os.path.isfile(os.path.join(l, f"appmanifest_{appid}.acf")) for l in libs)
