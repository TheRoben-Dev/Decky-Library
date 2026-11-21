"""Storage Sweep core: find what removed games left behind, and delete exactly that.

Safety rules (every delete goes through `delete()`):
- only direct children of <library>/steamapps/{shadercache,compatdata,workshop/content} whose
  name is a plain app id, never a symlink, never anything else;
- a game counts as installed if ANY library has its appmanifest OR libraryfolders.vdf lists it
  (so games on an SD card that isn't inserted right now are still treated as installed);
- Proton prefixes (compatdata) are only offered when every library is reachable, and never for
  non-Steam shortcuts (ids >= 2^31), because a prefix can hold saves that aren't in the cloud;
- nothing for the running game is touched.
"""
import os
import re
import shutil

KINDS = {
    "shadercache": ("steamapps", "shadercache"),
    "compatdata": ("steamapps", "compatdata"),
    "workshop": ("steamapps", "workshop", "content"),
}
SHORTCUT_MIN = 2 ** 31
# Steam tools/runtimes that keep their own compatdata/shadercache entries; never offered.
PROTECTED = {0, 228980}   # 228980 = Steamworks Common Redistributables

_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')
_APPS_BLOCK = re.compile(r'"apps"\s*\{([^}]*)\}', re.S)
_APP_ID = re.compile(r'"(\d+)"\s+"\d+"')


def steam_roots(home: str) -> list:
    out = []
    for c in (".local/share/Steam", ".steam/steam", ".steam/root"):
        p = os.path.join(home, c)
        if os.path.isdir(os.path.join(p, "steamapps")):
            rp = os.path.realpath(p)
            if rp not in out:
                out.append(rp)
    return out


def libraries(home: str) -> dict:
    """{"paths": [existing library roots], "missing": [listed but unreachable], "listed": set(appids)}"""
    roots = steam_roots(home)
    paths, missing, listed = list(roots), [], set()
    for root in roots:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="replace") as f:
                text = f.read(2_000_000)
        except OSError:
            continue
        for raw in _PATH.findall(text):
            p = raw.replace("\\\\", "\\")
            rp = os.path.realpath(p)
            if os.path.isdir(os.path.join(rp, "steamapps")):
                if rp not in paths:
                    paths.append(rp)
            elif rp not in missing:
                missing.append(rp)
        for block in _APPS_BLOCK.findall(text):
            listed.update(int(x) for x in _APP_ID.findall(block))
    return {"paths": paths, "missing": missing, "listed": listed}


def installed(libs: dict) -> set:
    ids = set(libs["listed"])
    for lib in libs["paths"]:
        try:
            for name in os.listdir(os.path.join(lib, "steamapps")):
                m = re.fullmatch(r"appmanifest_(\d+)\.acf", name)
                if m:
                    ids.add(int(m.group(1)))
        except OSError:
            pass
    return ids


def du(path: str) -> int:
    """Bytes on disk for a tree, without following symlinks (os.scandir: one stat per entry)."""
    total, stack = 0, [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            st = e.stat(follow_symlinks=False)
                            total += getattr(st, "st_blocks", 0) * 512 or st.st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def scan(home: str, known_shortcuts=(), running: int = 0) -> dict:
    libs = libraries(home)
    inst = installed(libs)
    # No installed games found at all means we're not reading Steam's files right; offer nothing.
    trust = bool(inst)
    shortcuts = {int(x) for x in known_shortcuts}
    entries = []
    for kind, parts in KINDS.items():
        for lib in libs["paths"]:
            base = os.path.join(lib, *parts)
            try:
                names = os.listdir(base)
            except OSError:
                continue
            for name in names:
                if not name.isdigit():
                    continue
                path = os.path.join(base, name)
                if os.path.islink(path) or not os.path.isdir(path):
                    continue
                appid = int(name)
                if appid in PROTECTED or appid == running:
                    continue
                is_shortcut = appid >= SHORTCUT_MIN
                if is_shortcut:
                    if kind != "shadercache":
                        continue
                    orphan = appid not in shortcuts and bool(shortcuts)
                else:
                    orphan = trust and appid not in inst
                if kind == "compatdata" and orphan and libs["missing"]:
                    orphan = False    # an unreachable library might hold this game
                size = du(path)
                if size == 0 and not orphan:
                    continue
                entries.append({"kind": kind, "appid": appid, "path": path, "bytes": size,
                                "orphan": orphan, "shortcut": is_shortcut})
    entries.sort(key=lambda e: -e["bytes"])
    return {"entries": entries, "libraries": libs["paths"], "missing": libs["missing"], "trusted": trust}


def _allowed(path: str, home: str) -> bool:
    # Paths come from scan() and are already canonical; anything with "..", a trailing slash or
    # a symlinked component is refused rather than resolved.
    if not isinstance(path, str) or os.path.realpath(path) != path:
        return False
    if os.path.islink(path) or not os.path.isdir(path):
        return False
    name = os.path.basename(path)
    if not name.isdigit() or int(name) in PROTECTED:
        return False
    parent = os.path.dirname(os.path.abspath(path))
    for lib in libraries(home)["paths"]:
        for parts in KINDS.values():
            if os.path.realpath(parent) == os.path.realpath(os.path.join(lib, *parts)) and \
                    os.path.dirname(os.path.realpath(path)) == os.path.realpath(parent):
                return True
    return False


def delete(paths: list, home: str, running: int = 0) -> dict:
    freed, done, failed = 0, [], []
    for p in paths:
        try:
            if running and os.path.basename(p) == str(int(running)):
                raise PermissionError("that game is running")
            if not _allowed(p, home):
                raise PermissionError("not a Steam cache folder")
            size = du(p)
            shutil.rmtree(p)
            freed += size
            done.append(p)
        except Exception as e:
            failed.append({"path": p, "error": str(e)})
    return {"freed": freed, "deleted": done, "failed": failed}
