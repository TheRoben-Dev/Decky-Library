"""Plugin settings stored as JSON in Decky's per-plugin settings folder."""
import json
import os

DEFAULTS = {
    "enabled": True,                 # keep the Library collection in sync
    "collectionName": "Handheld Ready",
    "deckMin": "playable",           # "verified" | "playable" | "off"
    "steamOS": True,                 # also accept Steam's "SteamOS Compatible" rating
    "native": False,                 # also accept games with a native Linux build
    "protonDB": "off",               # "off" | "gold" | "platinum"
    "controller": "partial",         # "partial" (partial or full) | "full"
    "excludeUnsupported": True,      # never include games Valve rates Unsupported on Deck
    "installedOnly": False,          # QAM list only
    "collectionId": "",              # id of the collection this plugin created (so renames follow it)
    "hiddenQamTabs": [],             # Quick Access tab keys to hide (strings; Decky's "999" is never hidden)
    "hiddenLibraryTabs": [],         # Steam Library tab ids to hide (e.g. "Soundtracks")
    "readyLibraryTab": False,        # show the Handheld Ready collection as a Library tab
}


def _coerce(d: dict) -> dict:
    out = dict(DEFAULTS)
    for k, v in (d or {}).items():
        if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
            out[k] = v
    if out["deckMin"] not in ("verified", "playable", "off"):
        out["deckMin"] = DEFAULTS["deckMin"]
    if out["protonDB"] not in ("off", "gold", "platinum"):
        out["protonDB"] = DEFAULTS["protonDB"]
    if out["controller"] not in ("partial", "full"):
        out["controller"] = DEFAULTS["controller"]
    out["hiddenQamTabs"] = sorted({str(k)[:32] for k in out["hiddenQamTabs"]
                                   if isinstance(k, (str, int)) and str(k) != "999"})[:64]
    out["hiddenLibraryTabs"] = sorted({str(k)[:64] for k in out["hiddenLibraryTabs"]
                                       if isinstance(k, str) and k})[:64]
    name = out["collectionName"].strip()[:64]
    out["collectionName"] = name or DEFAULTS["collectionName"]
    return out


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return _coerce(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(path: str, d: dict) -> dict:
    d = _coerce(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, path)
    return d
