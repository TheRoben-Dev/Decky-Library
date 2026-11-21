"""Downloads Amazon games file by file, checks every file's hash, updates in place, finds what
to launch.

Amazon serves each game as a signed manifest plus one download per file (named by its hash), so
there's no archive to unpack: files are written next to their final place as .part and renamed
once their hash matches. An interrupted install resumes: files already on disk with the right
size and hash are kept. Updates fetch only changed files and delete files the new version
dropped; anything else in the folder (saves, configs the game wrote) is left alone.
"""
import json
import math
import os
import re
import shutil
import stat
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import api, manifest

CHUNK = 1 << 20
WORKERS = 4                 # parallel file downloads; plenty for Wi-Fi, light on the CPU
RETRIES = 3
MAX_SCAN_FILES = 40_000
MAX_DEPTH = 6


class Cancelled(Exception):
    pass


class InstallError(Exception):
    pass


# ------------------------------------------------------------------ helpers

def clean_env() -> dict:
    """Decky's bundled Python sets LD_LIBRARY_PATH; system tools must not inherit it."""
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    return env


def slug(title: str, game_id: str) -> str:
    """Folder name: readable title plus a short stable suffix from the product id."""
    s = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().replace(" ", "-")
    s = re.sub(r"-{2,}", "-", s).strip("-.")[:60]
    return f"{s or 'game'}-{suffix(game_id)}"


def suffix(game_id: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(game_id).lower())[-8:] or "amzn"


def inside(root: str, path: str) -> bool:
    root = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == root or p.startswith(root + os.sep)


def free_bytes(path: str) -> int:
    p = path
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    try:
        return shutil.disk_usage(p or "/").free
    except OSError:
        return 0


def dir_size(path: str) -> int:
    total = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def rmtree(path: str) -> None:
    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
            func(p)
        except OSError:
            pass
    if os.path.lexists(path):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, onerror=onerror)
        else:
            os.unlink(path)


def safe_join(root: str, rel: str) -> str:
    """root/rel, refusing anything that would land outside root."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise InstallError(f"Unsafe path in the manifest: {rel[:80]}")
    p = os.path.join(root, *parts)
    if not inside(root, os.path.dirname(p)) and os.path.dirname(p) != root:
        raise InstallError(f"Unsafe path in the manifest: {rel[:80]}")
    return p


def file_hash(path: str, algo: str, want: str, cancel: threading.Event | None = None) -> str:
    h = manifest.hasher(algo)
    with open(path, "rb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return manifest.hexdigest(h, algo, want)


# ------------------------------------------------------------------ download

def fetch_manifest(base_url: str) -> tuple:
    raw = api.request(api.sub_url(base_url, "manifest.proto"), what="Amazon download server", raw=True, timeout=60)
    try:
        return manifest.parse(raw), raw
    except manifest.ManifestError as e:
        raise InstallError(str(e)) from None


def _get_file(base_url: str, f: dict, dest: str, cancel: threading.Event, tick) -> None:
    url = api.sub_url(base_url, "files", f["hash"])
    part = dest + ".part"
    last = None
    for attempt in range(RETRIES):
        if cancel.is_set():
            raise Cancelled()
        got = 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": api.UA})
            h = manifest.hasher(f["algo"])
            with urllib.request.build_opener(urllib.request.HTTPSHandler(context=api.context())).open(req, timeout=60) as r, \
                    open(part, "wb") as out:
                while True:
                    if cancel.is_set():
                        raise Cancelled()
                    b = r.read(CHUNK)
                    if not b:
                        break
                    out.write(b)
                    h.update(b)
                    got += len(b)
                    tick(len(b))
            if manifest.hexdigest(h, f["algo"], f["hash"]) != f["hash"]:
                raise InstallError(f"{os.path.basename(dest)} arrived damaged")
            os.replace(part, dest)
            return
        except Cancelled:
            _unlink(part)
            tick(-got)
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, InstallError, OSError) as e:
            _unlink(part)
            tick(-got)
            if isinstance(e, OSError) and getattr(e, "errno", 0) == 28:
                raise InstallError("The drive is full") from None
            last = e
            time.sleep(1.5 * (attempt + 1))
    reason = getattr(last, "reason", None) or last
    raise InstallError(f"Couldn't download {os.path.basename(dest)} ({reason})")


def _unlink(p: str) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass


def sync_files(base_url: str, files: list, root: str, cancel: threading.Event, progress, verify_existing: bool = True) -> int:
    """Makes every file in `files` present under root with the right hash. progress(done, total)
    is called at most a few times a second. Returns bytes downloaded."""
    total = sum(f["size"] for f in files)
    state = {"done": 0, "net": 0, "t": 0.0}
    lock = threading.Lock()

    def tick(n: int):
        with lock:
            state["done"] += n
            state["net"] += n
            now = time.monotonic()
            if now - state["t"] >= 0.4:
                state["t"] = now
                progress(state["done"], total)

    todo = []
    for f in files:
        if cancel.is_set():
            raise Cancelled()
        dest = safe_join(root, f["path"])
        # Resume: a file that's already complete costs a hash check instead of a download.
        if verify_existing and os.path.isfile(dest) and os.path.getsize(dest) == f["size"]:
            try:
                if file_hash(dest, f["algo"], f["hash"], cancel) == f["hash"]:
                    with lock:
                        state["done"] += f["size"]
                    continue
            except OSError:
                pass
        todo.append((f, dest))
    progress(state["done"], total)
    for d in sorted({os.path.dirname(dest) for _f, dest in todo}):
        os.makedirs(d, exist_ok=True)

    # Biggest files first so the workers finish together.
    todo.sort(key=lambda x: x[0]["size"], reverse=True)
    errors: list = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(_get_file, base_url, f, dest, cancel, tick) for f, dest in todo]
        for fut in futs:
            try:
                fut.result()
            except Cancelled:
                cancel.set()
            except Exception as e:      # stop the rest on the first real error
                errors.append(e)
                cancel.set()
    if errors:
        e = errors[0]
        raise e if isinstance(e, InstallError) else InstallError(str(e))
    if cancel.is_set():
        raise Cancelled()
    progress(total, total)
    return state["net"]


def remove_files(root: str, paths: list) -> None:
    """Deletes files an update dropped, then any folders left empty by that."""
    dirs = set()
    for rel in paths:
        try:
            p = safe_join(root, rel)
        except InstallError:
            continue
        if os.path.isfile(p) or os.path.islink(p):
            _unlink(p)
            dirs.add(os.path.dirname(p))
    for d in sorted(dirs, key=len, reverse=True):
        while inside(root, d) and os.path.realpath(d) != os.path.realpath(root):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)


# ------------------------------------------------------------------ what to launch

def _json5(text: str):
    """fuel.json is JSON5-ish: allow comments and trailing commas."""
    out, i, n, in_str, q = [], 0, len(text), False, ""
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == q:
                in_str = False
            i += 1
            continue
        if c in "\"'":
            in_str, q = True, c
            out.append('"' if c == "'" else c)
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    s = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    return json.loads(s)


def fuel(root: str) -> dict:
    """Launch info from the game's fuel.json: {exe, args, cwd, post} (exe/cwd absolute) or {}."""
    p = os.path.join(root, "fuel.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            data = _json5(f.read(262144))
    except (OSError, ValueError):
        return {}
    main = data.get("Main") if isinstance(data, dict) else None
    if not isinstance(main, dict) or not isinstance(main.get("Command"), str):
        return {}
    try:
        exe = safe_join(root, main["Command"])
    except InstallError:
        return {}
    args = [str(a) for a in main.get("Args") or [] if isinstance(a, (str, int, float))]
    cwd = root
    sub = main.get("WorkingSubdirOverride")
    if isinstance(sub, str) and sub.strip():
        try:
            cwd = safe_join(root, sub)
        except InstallError:
            pass
    post = [a for a in data.get("PostInstall") or [] if isinstance(a, dict) and a.get("Command")]
    return {"exe": exe, "args": args, "cwd": cwd, "post": len(post)}


def quote_args(args: list) -> str:
    return " ".join(f'"{a}"' if (" " in a or not a) else a for a in (x.replace('"', "") for x in args))


HELPERS = re.compile(
    r"(?i)(unins.*\.exe$|unitycrashhandler|crashpad_handler|crashreport|vcredist|vc_redist|dxwebsetup|dxsetup|"
    r"directx|oalinst|physx|dotnet|ue4prereq|uninstall|setup|launcher_helper|easyanticheat|eac_launcher|"
    r"\.vshost\.exe$|^python[0-9.]*\.exe$|^java(w)?\.exe$)")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def scan(root: str, title: str) -> list:
    """Windows executables under root, best first: [{path (absolute), score, size}]."""
    tnorm = _norm(title)
    words = re.findall(r"[a-z0-9]{3,}", title.lower())
    out, count = [], 0
    root = os.path.realpath(root)
    for dp, dn, fn in os.walk(root):
        depth = dp[len(root):].count(os.sep)
        dn[:] = [d for d in dn if depth < MAX_DEPTH and d.lower() not in
                 ("redist", "_commonredist", "directx", "vcredist", "__installer", "support", "prereqs")]
        for n in fn:
            count += 1
            if count > MAX_SCAN_FILES:
                break
            low = n.lower()
            if not low.endswith(".exe"):
                continue
            p = os.path.join(dp, n)
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            score = -depth * 10 + min(20.0, math.log2(max(size, 1)) - 10)
            if HELPERS.search(low):
                score -= 60
            stem = _norm(os.path.splitext(n)[0])
            if tnorm and stem and (stem in tnorm or tnorm in stem):
                score += 30
            elif any(w in low for w in words):
                score += 12
            if "shipping" in low:
                score += 15
            out.append({"path": p, "score": round(score, 1), "size": size})
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


def win_path(path: str) -> str:
    """How a Windows program running under Proton sees a Linux path (Z: is /)."""
    return "Z:" + os.path.realpath(path).replace("\\", "/")
