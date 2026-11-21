"""Download and unpack GOG installers, find the game's executable, carry saves across updates.

Linux installers are unpacked in pure Python (zipfile); Windows installers with innoextract when
it's installed. Every extracted path is checked to stay inside the game's folder. Nothing here runs
unless a download/install was asked for.
"""
import math
import os
import re
import shutil
import stat
import subprocess
import json
import threading
import time
import zipfile

from . import api

CHUNK = 1 << 20
MAX_SCAN_FILES = 40_000
MAX_DEPTH = 6
STATE_DIR = ".gog-library"   # never created inside game folders; kept as a name to skip


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


def which(*names: str) -> str | None:
    for n in names:
        for d in ("/usr/bin", "/usr/local/bin", "/bin", os.path.expanduser("~/.local/bin")):
            p = os.path.join(d, n)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def slug(title: str, game_id: int) -> str:
    s = re.sub(r"[^A-Za-z0-9._ -]+", "", title).strip().replace(" ", "-")
    s = re.sub(r"-{2,}", "-", s).strip("-.")[:60]
    return f"{s or 'game'}-{int(game_id)}"


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


# ------------------------------------------------------------------ download

def download(url: str, size: int, dest: str, progress, cancel: threading.Event, base: int = 0) -> str:
    """Streams a CDN file to dest (a .part file renamed when complete). progress(done) gets bytes
    so far, plus `base` (for installers split into several files)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    r = api.open_url(url, timeout=30)
    try:
        total = int(r.headers.get("Content-Length") or 0) or int(size or 0)
        done = 0
        last = 0.0
        with open(part, "wb") as f:
            while True:
                if cancel.is_set():
                    raise Cancelled()
                buf = r.read(CHUNK)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                now = time.monotonic()
                if now - last >= 0.25:
                    progress(base + done)
                    last = now
        progress(base + done)
        if total and done < total:
            raise InstallError("The download ended early; try again")
    except BaseException:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
    finally:
        r.close()
    os.replace(part, dest)
    return dest


# ------------------------------------------------------------------ unpack

def _safe_name(name: str) -> str | None:
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or name.startswith("/"):
        return None
    return os.path.join(*parts)


def _unzip(src: str, dest: str, cancel: threading.Event, prefix: str = "") -> None:
    """prefix: only members under it, with it stripped (GOG Linux installers: data/noarch/)."""
    with zipfile.ZipFile(src) as z:   # also reads zips with a shell script in front
        infos = [i for i in z.infolist() if i.filename.startswith(prefix) and len(i.filename) > len(prefix)]
        need = sum(i.file_size for i in infos)
        if need > free_bytes(dest) - 128 * 1024 * 1024:
            raise InstallError(f"Not enough free space to unpack ({need // (1024 * 1024)} MB needed)")
        for i in infos:
            if cancel.is_set():
                raise Cancelled()
            rel = _safe_name(i.filename[len(prefix):])
            if not rel:
                continue
            out = os.path.join(dest, rel)
            if not inside(dest, os.path.dirname(out) or dest):
                continue
            mode = (i.external_attr >> 16) & 0xFFFF
            if i.is_dir():
                os.makedirs(out, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if stat.S_ISLNK(mode):
                target = z.read(i).decode("utf-8", "replace")
                if inside(dest, os.path.join(os.path.dirname(out), target)) and not os.path.lexists(out):
                    os.symlink(target, out)
                continue
            with z.open(i) as fi, open(out, "wb") as fo:
                shutil.copyfileobj(fi, fo, CHUNK)
            # zipfile drops Unix permissions; put the executable bits back.
            if mode & 0o111:
                os.chmod(out, 0o755)


def _run(cmd: list, what: str, cancel: threading.Event) -> None:
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=clean_env())
    while True:
        try:
            _out, err = p.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel.is_set():
                p.kill()
                p.wait()
                raise Cancelled()
    if p.returncode != 0:
        msg = (err or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise InstallError(f"{what} failed: {msg[0][:160]}")


def _check_tree(dest: str) -> None:
    """External tools are trusted less: drop anything that points outside the folder."""
    for dp, dn, fn in os.walk(dest):
        for n in dn + fn:
            p = os.path.join(dp, n)
            if os.path.islink(p) and not inside(dest, p):
                os.unlink(p)


def windows_installer(path: str) -> str:
    """'inno', 'nsis', or '' for a Windows .exe, from markers in its first few MB."""
    try:
        with open(path, "rb") as f:
            head = f.read(4 * 1024 * 1024)
    except OSError:
        return ""
    if b"Inno Setup" in head:
        return "inno"
    if b"Nullsoft" in head or b"NullsoftInst" in head:
        return "nsis"
    return ""


def extract_linux(src: str, dest: str, cancel: threading.Event) -> None:
    """GOG Linux installers are MojoSetup scripts with a zip appended; the game is data/noarch/."""
    try:
        _unzip(src, dest, cancel, "data/noarch/")
    except zipfile.BadZipFile:
        raise InstallError("The Linux installer couldn't be read; try again") from None
    if not os.listdir(dest):
        raise InstallError("The Linux installer was empty")


def extract_windows(exe: str, dest: str, cancel: threading.Event) -> bool:
    """Unpacks a GOG Windows (Inno Setup) installer with innoextract when it's installed.
    False when it isn't, or the installer couldn't be unpacked: it then runs once through Proton."""
    tool = which("innoextract")
    if not tool or windows_installer(exe) != "inno":
        return False
    out = os.path.join(dest, ".unpack")
    try:
        os.makedirs(out, exist_ok=True)
        _run([tool, "-s", "-m", "-d", out, exe], "innoextract", cancel)
        _check_tree(out)
        src = os.path.join(out, "app") if os.path.isdir(os.path.join(out, "app")) else out
        if not any(c["kind"] == "windows" for c in scan(src, "", [])[:1]):
            rmtree(out)
            return False
        for n in os.listdir(src):
            if n in ("tmp", "commonappdata", "__support") and src == out:
                continue
            target = os.path.join(dest, n)
            if not os.path.lexists(target):
                os.replace(os.path.join(src, n), target)
        rmtree(out)
        return True
    except Cancelled:
        rmtree(out)
        raise
    except Exception:
        rmtree(out)
        return False


# ------------------------------------------------------------------ executables

HELPERS = re.compile(
    r"(?i)(unins.*\.exe$|unitycrashhandler|crashpad_handler|crashreport|chrome-sandbox|nacl_helper|"
    r"notification_helper|vcredist|vc_redist|dxwebsetup|dxsetup|directx|oalinst|physx|dotnet|ue4prereq|"
    r"uninstall|setup_helper|\.vshost\.exe$|nwjc\.exe$|flixel\.exe$|kick\.bin$|zsync|"
    r"^python[0-9.]*(\.exe)?$|^pythonw(\.exe)?$|^java(w)?(\.exe)?$|^node(\.exe)?$|^lua(\.exe)?$)")
SO_RE = re.compile(r"(?i)\.so(\.\d+)*$|\.dll$|\.dylib$")
LINUX_EXT = (".x86_64", ".x86", ".sh", ".appimage", ".bin", ".run")


def _elf(path: str) -> dict | None:
    try:
        with open(path, "rb") as f:
            h = f.read(20)
    except OSError:
        return None
    if len(h) < 20 or h[:4] != b"\x7fELF":
        return None
    little = h[5] == 1
    etype = int.from_bytes(h[16:18], "little" if little else "big")
    machine = int.from_bytes(h[18:20], "little" if little else "big")
    return {"bits": 64 if h[4] == 2 else 32, "type": etype, "machine": machine}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def scan(root: str, title: str, targets: list, prefer: str = "") -> list:
    """Executables under root, best first: [{path (relative), kind 'linux'|'windows', score, args}]."""
    tnorm = _norm(title)
    words = [w for w in re.findall(r"[a-z0-9]{3,}", title.lower())]
    hinted = {}
    for t in targets or []:
        if isinstance(t, dict) and t.get("path"):
            hinted[str(t["path"]).replace("\\", "/")] = t
    out = []
    count = 0
    root = os.path.realpath(root)
    for dp, dn, fn in os.walk(root):
        depth = dp[len(root):].count(os.sep)
        dn[:] = [d for d in dn if d != STATE_DIR and not d.startswith(".") and depth < MAX_DEPTH
                 and d.lower() not in ("__macosx", "redist", "_commonredist", "directx", "vcredist")]
        for n in fn:
            count += 1
            if count > MAX_SCAN_FILES:
                break
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root)
            low = n.lower()
            if os.path.islink(p) or SO_RE.search(low):
                continue
            kind = None
            score = 0.0
            if low.endswith(".exe"):
                kind = "windows"
            else:
                e = _elf(p)
                if e:
                    if e["machine"] not in (0x3E, 0x03):     # x86-64 / i386 only
                        continue
                    if e["type"] not in (2, 3):
                        continue
                    kind = "linux"
                    score += 8 if e["bits"] == 64 else -15
                    if e["type"] == 3 and not os.access(p, os.X_OK) and not low.endswith(LINUX_EXT):
                        continue   # most likely a shared library without a .so name
                elif low.endswith((".sh", ".x86_64", ".appimage")):
                    kind = "linux"
            if not kind:
                continue
            if HELPERS.search(low):
                score -= 60
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            score -= depth * 10
            score += min(20.0, math.log2(max(size, 1)) - 10)
            stem = _norm(os.path.splitext(n)[0])
            if tnorm and stem and (stem in tnorm or tnorm in stem):
                score += 30
            elif any(w in low for w in words):
                score += 12
            if low.endswith(".x86_64"):
                score += 10
            if low.endswith(".sh"):
                score += 4
            if re.search(r"(?i)(32|x86\b|i386)", low) and not low.endswith(".x86_64"):
                score -= 6
            if rel.replace(os.sep, "/") in hinted:
                score += 100
            if prefer and kind == prefer:
                score += 25
            out.append({"path": rel, "kind": kind, "score": round(score, 1), "size": size, "args": ""})
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


def ci_path(root: str, rel: str) -> str:
    """root/rel, matching each part case-insensitively like Windows does."""
    cur = root
    for part in [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]:
        if part == "..":
            return ""
        hit = part
        try:
            for n in os.listdir(cur):
                if n.lower() == part.lower():
                    hit = n
                    break
        except OSError:
            pass
        cur = os.path.join(cur, hit)
    return cur


def play_task(root: str, game_id: int) -> dict | None:
    """The primary launch entry from the game's goggame-<id>.info (what Galaxy's Play button runs)."""
    try:
        names = os.listdir(root)
    except OSError:
        return None
    infos = [n for n in names if n.lower() == f"goggame-{int(game_id)}.info"]
    infos += [n for n in names if n.lower().startswith("goggame-") and n.lower().endswith(".info") and n not in infos]
    for n in infos:
        try:
            with open(os.path.join(root, n), encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        tasks = [t for t in data.get("playTasks") or [] if isinstance(t, dict) and t.get("path")
                 and t.get("type", "FileTask") == "FileTask"]
        tasks.sort(key=lambda t: (not t.get("isPrimary"), t.get("category", "game") != "game"))
        for t in tasks:
            exe = ci_path(root, str(t["path"]))
            if exe and os.path.isfile(exe) and inside(root, exe):
                wd = ci_path(root, str(t.get("workingDir") or "")) if t.get("workingDir") else os.path.dirname(exe)
                args = t.get("arguments") or ""
                if isinstance(args, list):
                    args = " ".join(f'"{a}"' if " " in str(a) else str(a) for a in args)
                return {"exe": exe, "args": str(args), "workdir": wd if wd and inside(root, wd) else os.path.dirname(exe)}
    return None


def make_executable(path: str) -> None:
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


# ------------------------------------------------------------------ receipts / updates

def file_list(root: str) -> list:
    out = []
    for dp, _dn, fn in os.walk(root):
        for n in fn:
            out.append(os.path.relpath(os.path.join(dp, n), root))
    return sorted(out)


def carry_over(old: str, new: str, receipt: list | None) -> int:
    """Copies files the game created in its folder (saves, configs) into the new version.
    With a receipt (the files the previous version shipped), everything not on it is the
    game's own. Without one, files the new version doesn't ship are kept."""
    shipped = set(receipt) if receipt is not None else None
    moved = 0
    for rel in file_list(old):
        if shipped is not None and rel in shipped:
            continue
        dst = os.path.join(new, rel)
        if os.path.lexists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.replace(os.path.join(old, rel), dst)
            moved += 1
        except OSError:
            try:
                shutil.copy2(os.path.join(old, rel), dst)
                moved += 1
            except OSError:
                pass
    return moved
