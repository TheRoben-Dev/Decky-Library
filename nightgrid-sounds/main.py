"""Nightgrid Sounds - Decky backend.

Only stores the settings (one small JSON file). The sounds are synthesized and swapped in the
frontend (src/sounds.ts, src/engine.ts); nothing here runs in the background.
"""
import json
import os
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


class Plugin:
    async def get_config(self):
        return load()

    async def set_config(self, cfg: dict):
        return save(cfg)

    async def _main(self):
        pass

    async def _unload(self):
        pass
