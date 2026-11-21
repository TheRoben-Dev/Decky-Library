"""Applies bundled movies as Steam's startup / suspend overrides.

Steam (Game Mode) plays override videos from <Steam>/config/uioverrides/movies. Which file name it
reads depends on the device (Steam Deck LCD/OLED, other SteamOS-style handhelds, Big Picture), so
every name gets the same video, the way Bazzite installs its own videos (see Bazzite's
/usr/bin/steam-tweaks). Bazzite only copies its videos where a file is missing, so ours stay.
Files are copied (not linked) so they keep working if the plugin is removed mid-way; every file we
write is remembered by SHA-256, so a file someone else put there (another plugin, by hand) is
never deleted: it's moved aside to `<name>.before-nightgrid` and put back when ours is turned off.
"""
import hashlib
import json
import os
import random
import shutil

TARGETS = {
    "boot": ["deck_startup.webm", "steam_os_startup.webm", "bigpicture_startup.webm", "oled_startup.webm"],
    "suspend": ["steam_os_suspend.webm", "steam_os_suspend_from_throbber.webm",
                "deck-suspend-animation.webm", "deck-suspend-animation-from-throbber.webm",
                "oled-suspend-animation.webm", "oled-suspend-animation-from-throbber.webm"],
}


def find_override_dir(home: str) -> str:
    """<Steam>/config/uioverrides/movies. ~/.local/share/Steam is the real folder on Bazzite and
    SteamOS (~/.steam/root links to it); fall back to ~/.steam/root, then ~/.steam/steam."""
    for base in (os.path.join(home, ".local", "share", "Steam"), os.path.join(home, ".steam", "root"),
                 os.path.join(home, ".steam", "steam")):
        if os.path.isdir(os.path.join(base, "config")):
            return os.path.join(os.path.realpath(base), "config", "uioverrides", "movies")
    return os.path.join(home, ".local", "share", "Steam", "config", "uioverrides", "movies")
BACKUP_SUFFIX = ".before-nightgrid"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_catalog(movies_dir: str) -> dict:
    with open(os.path.join(movies_dir, "movies.json"), encoding="utf-8") as f:
        cat = json.load(f)
    out = {}
    for kind in TARGETS:
        out[kind] = [m for m in cat.get(kind, []) if os.path.isfile(os.path.join(movies_dir, m["file"]))]
    return out


def with_thumbs(cat: dict, movies_dir: str) -> dict:
    """Adds a small JPEG thumbnail (data: URI) from movies/thumbs/<id>.jpg to each movie."""
    import base64
    out = {}
    for kind, movies in cat.items():
        out[kind] = []
        for m in movies:
            p = os.path.join(movies_dir, "thumbs", f"{m['id']}.jpg")
            thumb = None
            if os.path.isfile(p) and os.path.getsize(p) < 64 * 1024:
                with open(p, "rb") as f:
                    thumb = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
            out[kind].append({**m, "thumb": thumb})
    return out


SAVER_STYLES = ("random", "grid", "signal", "terminal", "clock")
SAVER_MINUTES = (1, 2, 3, 5, 10, 15, 30)


def clean_saver(d: dict) -> dict:
    """Screensaver settings with defaults and only allowed values."""
    m = d.get("minutes", 5)
    return {
        "enabled": bool(d.get("enabled", True)),
        "minutes": m if m in SAVER_MINUTES else 5,
        "style": d.get("style") if d.get("style") in SAVER_STYLES else "random",
    }


class Store:
    """settings.json: {"boot": id|"", "suspend": id|"", "shuffle": bool, "written": {filename: sha}}"""

    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("boot", "")
        self.data.setdefault("suspend", "")
        self.data.setdefault("shuffle", False)
        self.data.setdefault("written", {})
        saver = self.data.get("saver") if isinstance(self.data.get("saver"), dict) else {}
        self.data["saver"] = clean_saver(saver)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)


def target_state(override_dir: str, name: str, written: dict) -> str:
    """'none' | 'ours' | 'other' for one override file."""
    p = os.path.join(override_dir, name)
    if not os.path.lexists(p):
        return "none"
    if os.path.islink(p) or not os.path.isfile(p):
        return "other"
    return "ours" if written.get(name) and sha256_file(p) == written[name] else "other"


def _clear(override_dir: str, name: str, store: Store):
    """Removes our file (or moves someone else's aside once) so the slot is free."""
    p = os.path.join(override_dir, name)
    st = target_state(override_dir, name, store.data["written"])
    if st == "ours":
        os.remove(p)
    elif st == "other":
        bak = p + BACKUP_SUFFIX
        if os.path.lexists(bak):
            # a backup already exists: keep the oldest one, drop this newer foreign file
            os.remove(p)
        else:
            os.rename(p, bak)
    store.data["written"].pop(name, None)


def apply(kind: str, movie_id: str, movies_dir: str, override_dir: str, store: Store) -> dict:
    """Sets the movie for `kind` ('' = back to Steam's own, restoring anything we moved aside)."""
    if kind not in TARGETS:
        raise ValueError(f"unknown kind {kind!r}")
    cat = load_catalog(movies_dir)
    movie = None
    if movie_id:
        movie = next((m for m in cat[kind] if m["id"] == movie_id), None)
        if movie is None:
            raise ValueError(f"no {kind} movie {movie_id!r}")
    os.makedirs(override_dir, exist_ok=True)
    for name in TARGETS[kind]:
        p = os.path.join(override_dir, name)
        if movie is None:
            if target_state(override_dir, name, store.data["written"]) == "ours":
                os.remove(p)
            store.data["written"].pop(name, None)
            bak = p + BACKUP_SUFFIX
            if os.path.lexists(bak) and not os.path.lexists(p):
                os.rename(bak, p)
            continue
        _clear(override_dir, name, store)
        src = os.path.join(movies_dir, movie["file"])
        tmp = p + ".nightgrid-tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, p)
        store.data["written"][name] = sha256_file(p)
    store.data[kind] = movie_id
    store.save()
    return status(movies_dir, override_dir, store)


def shuffle_boot(movies_dir: str, override_dir: str, store: Store, rnd=random) -> str:
    """Picks a different startup movie than last time (if there's more than one)."""
    ids = [m["id"] for m in load_catalog(movies_dir)["boot"]]
    if not ids:
        return ""
    choices = [i for i in ids if i != store.data["boot"]] or ids
    pick = rnd.choice(choices)
    apply("boot", pick, movies_dir, override_dir, store)
    return pick


def status(movies_dir: str, override_dir: str, store: Store) -> dict:
    cat = load_catalog(movies_dir)
    states = {}
    for kind, names in TARGETS.items():
        s = [target_state(override_dir, n, store.data["written"]) for n in names]
        states[kind] = "ours" if all(x == "ours" for x in s) else "other" if "other" in s else \
                       "partial" if "ours" in s else "none"
    # a selection whose files were replaced behind our back no longer counts as applied
    sel = {k: (store.data[k] if states[k] == "ours" else "") for k in TARGETS}
    return {"catalog": with_thumbs(cat, movies_dir), "boot": sel["boot"], "suspend": sel["suspend"], "shuffle": bool(store.data["shuffle"]),
            "states": states, "overrideDir": override_dir, "saver": store.data["saver"]}


def restore_all(movies_dir: str, override_dir: str, store: Store):
    for kind in TARGETS:
        apply(kind, "", movies_dir, override_dir, store)


CHUNK = 768 * 1024


def movie_chunk(movies_dir: str, movie_id: str, offset: int) -> dict:
    """One base64 piece of a bundled video, for the in-plugin preview."""
    import base64
    cat = load_catalog(movies_dir)
    movie = next((m for k in TARGETS for m in cat[k] if m["id"] == movie_id), None)
    if movie is None:
        raise ValueError(f"no movie {movie_id!r}")
    path = os.path.join(movies_dir, movie["file"])
    size = os.path.getsize(path)
    offset = max(0, int(offset))
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read(CHUNK)
    return {"data": base64.b64encode(data).decode("ascii"), "size": size, "next": offset + len(data),
            "done": offset + len(data) >= size}


def repair(movies_dir: str, override_dir: str, store: Store) -> list:
    """Re-applies a selection that only partly holds (e.g. after an update added more file names,
    or Bazzite filled in a name we didn't write yet). A slot with none of our files is left alone,
    since then someone else chose to replace it."""
    fixed = []
    for kind, names in TARGETS.items():
        sel = store.data.get(kind)
        if not sel:
            continue
        st = [target_state(override_dir, n, store.data["written"]) for n in names]
        if "ours" in st and any(x != "ours" for x in st):
            apply(kind, sel, movies_dir, override_dir, store)
            fixed.append(kind)
    return fixed
