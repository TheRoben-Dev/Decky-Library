"""Nightgrid Sounds - Decky backend.

Stores the settings, and keeps the rendered sound files where Steam's UI can load them.

The frontend synthesizes each pack (src/sounds.ts) and sends the WAVs here once per
pack+volume. They're written to <plugin data>/sounds/<key>/ and exposed to Steam through a
symlink <steam>/steamui/sounds_nightgrid -> <plugin data>/sounds, because Steam's sound player
only plays URLs it can load from its own UI folder (blob: URLs end up silent). The link is
re-created on every start since Steam updates can wipe steamui. Nothing runs in the background.
"""
import base64
import json
import os
import re
import shutil
import tempfile

import decky

PACKS = ("nightgrid", "pulse", "static", "glass")
CATS = ("nav", "select", "open", "close", "tab", "edge", "toggleOn", "toggleOff",
        "sliderUp", "sliderDown", "notify", "launch", "type")
MODES = ("pack", "steam", "off")
DEFAULTS = {"enabled": True, "pack": "nightgrid", "volume": 0.8, "cats": {}}


def clean(d) -> dict:
    out = json.loads(json.dumps(DEFAULTS))
    if not isinstance(d, dict):
        return out
    if isinstance(d.get("enabled"), bool):
        out["enabled"] = d["enabled"]
    if d.get("pack") in PACKS:
        out["pack"] = d["pack"]
    v = d.get("volume")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        out["volume"] = round(min(1.0, max(0.0, float(v))), 2)
    if isinstance(d.get("cats"), dict):
        out["cats"] = {k: m for k, m in d["cats"].items() if k in CATS and m in MODES and m != "pack"}
    return out


def _path() -> str:
    return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except Exception:
        return clean(None)


def save(d: dict) -> dict:
    d = clean(d)
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_path()), prefix=".settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, _path())
    return d


LINK_NAME = "sounds_nightgrid"
MAX_WAV = 2_000_000
_KEY = re.compile(r"[a-z0-9-]{1,40}")


def steamui_dir(home: str):
    for c in (".local/share/Steam", ".steam/steam", ".steam/root"):
        p = os.path.join(home, c, "steamui")
        if os.path.isdir(p):
            return os.path.realpath(p)
    return None


def sounds_dir() -> str:
    return os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "sounds")


def ensure_link(home: str, target: str) -> str:
    """Make <steamui>/sounds_nightgrid point at target. Returns the URL prefix Steam uses."""
    ui = steamui_dir(home)
    if not ui:
        raise RuntimeError("Steam's UI folder (steamui) wasn't found")
    os.makedirs(target, exist_ok=True)
    link = os.path.join(ui, LINK_NAME)
    if os.path.islink(link):
        if os.path.realpath(link) == os.path.realpath(target):
            return f"/{LINK_NAME}/"
        os.unlink(link)
    elif os.path.exists(link):
        raise RuntimeError(f"{link} exists and isn't ours; not touching it")
    os.symlink(target, link, target_is_directory=True)
    return f"/{LINK_NAME}/"


def have(key: str, names) -> bool:
    d = os.path.join(sounds_dir(), key)
    return all(os.path.isfile(os.path.join(d, f"{n}.wav")) for n in names)


def write_set(key: str, files: dict) -> None:
    """Write one pack+volume set, then drop every other set (only one is ever in use)."""
    if not _KEY.fullmatch(key):
        raise ValueError("bad key")
    root = sounds_dir()
    os.makedirs(root, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=root, prefix=".new-")
    try:
        for name, b64 in files.items():
            if name not in CATS and name != "silent":
                raise ValueError(f"unknown sound {name}")
            raw = base64.b64decode(b64, validate=True)
            if len(raw) > MAX_WAV or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
                raise ValueError(f"{name} isn't a WAV file")
            with open(os.path.join(tmp, f"{name}.wav"), "wb") as f:
                f.write(raw)
        dest = os.path.join(root, key)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.replace(tmp, dest)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    for other in os.listdir(root):
        if other != key:
            shutil.rmtree(os.path.join(root, other), ignore_errors=True)


class Plugin:
    async def get_config(self):
        return load()

    async def set_config(self, cfg: dict):
        return save(cfg)

    async def prepare(self, key: str):
        """Link Steam's UI folder to our sounds and say whether this pack+volume is on disk."""
        try:
            base = ensure_link(decky.DECKY_USER_HOME, sounds_dir())
            return {"ok": True, "base": base, "have": bool(_KEY.fullmatch(key or "")) and have(key, CATS + ("silent",))}
        except Exception as e:
            decky.logger.error(f"prepare failed: {e}")
            return {"ok": False, "error": str(e)}

    async def store_sounds(self, key: str, files: dict):
        try:
            write_set(key, files or {})
            return {"ok": True}
        except Exception as e:
            decky.logger.error(f"store_sounds failed: {e}")
            return {"ok": False, "error": str(e)}

    async def _main(self):
        pass

    async def _unload(self):
        pass

    async def _uninstall(self):
        ui = steamui_dir(decky.DECKY_USER_HOME)
        link = ui and os.path.join(ui, LINK_NAME)
        if link and os.path.islink(link):
            os.unlink(link)
