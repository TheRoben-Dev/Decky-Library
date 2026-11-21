"""Download, unpack, find the game's executable, update in place, uninstall.

Pure Python (zipfile/tarfile) for the common archive types; 7-Zip, bsdtar, unrar or innoextract
are used only when an archive needs them and they're installed. Every extracted path is checked to
stay inside the game's folder. Nothing here runs unless a download/install was asked for.
"""
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import zipfile

from . import api

CHUNK = 1 << 20
MAX_SCAN_FILES = 40_000
MAX_DEPTH = 6
STATE_DIR = ".itch-library"   # never created inside game folders; kept as a name to skip


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

def download(key: str, upload: dict, download_key: int, dest: str, progress, cancel: threading.Event) -> str:
    """Streams the upload to dest (a .part file renamed when complete). progress(done, total)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    r = api.open_download(key, upload["id"], download_key)
    try:
        total = int(r.headers.get("Content-Length") or 0) or int(upload.get("size") or 0)
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
                    progress(done, total)
                    last = now
        progress(done, total)
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

def sniff(path: str) -> str:
    with open(path, "rb") as f:
        h = f.read(264)
    if h[:4] == b"PK\x03\x04" or h[:4] == b"PK\x05\x06":
        return "zip"
    if h[:2] == b"\x1f\x8b" or h[:3] == b"BZh" or h[:6] == b"\xfd7zXZ\x00":
        return "tar"
    if h[:4] == b"\x28\xb5\x2f\xfd":
        return "zstd"
    if h[257:262] == b"ustar":
        return "tar"
    if h[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if h[:4] == b"Rar!":
        return "rar"
    if h[:4] == b"\x7fELF":
        return "elf"
    if h[:2] == b"MZ":
        return "pe"
    if h[:2] == b"#!":
        return "script"
    if h[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "msi"
    low = path.lower()
    if low.endswith(".dmg"):
        return "dmg"
    if low.endswith(".apk"):
        return "apk"
    return "unknown"


def _safe_name(name: str) -> str | None:
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or name.startswith("/"):
        return None
    return os.path.join(*parts)


def _unzip(src: str, dest: str, cancel: threading.Event) -> None:
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        need = sum(i.file_size for i in infos)
        if need > free_bytes(dest) - 128 * 1024 * 1024:
            raise InstallError(f"Not enough free space to unpack ({need // (1024 * 1024)} MB needed)")
        for i in infos:
            if cancel.is_set():
                raise Cancelled()
            rel = _safe_name(i.filename)
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


def _untar(src: str, dest: str, cancel: threading.Event) -> None:
    try:
        import tarfile
    except ImportError:
        tar = which("tar", "bsdtar")
        if not tar:
            raise InstallError("Can't unpack .tar archives on this system")
        _run([tar, "-xf", src, "-C", dest], "tar", cancel)
        _check_tree(dest)
        return
    with tarfile.open(src) as t:
        members = []
        for m in t:
            if cancel.is_set():
                raise Cancelled()
            rel = _safe_name(m.name)
            if not rel or m.isdev() or m.isfifo():
                continue
            if (m.issym() or m.islnk()) and not inside(dest, os.path.join(dest, os.path.dirname(rel), m.linkname)):
                continue
            m.name = rel
            members.append(m)
        kw = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        t.extractall(dest, members=members, **kw)


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


def _external(src: str, dest: str, kind: str, cancel: threading.Event) -> None:
    sz = which("7z", "7za", "7zz")
    bsd = which("bsdtar")
    if kind == "rar":
        unrar = which("unrar")
        if unrar:
            return _run([unrar, "x", "-o+", "-idq", src, dest + os.sep], "unrar", cancel)
    if sz:
        return _run([sz, "x", "-y", "-bd", f"-o{dest}", src], "7-Zip", cancel)
    if bsd:
        return _run([bsd, "-xf", src, "-C", dest], "bsdtar", cancel)
    raise InstallError(f"This game comes as a .{kind} archive, which needs 7-Zip (7z) or bsdtar on the system")


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


def unpack(src: str, dest: str, filename: str, cancel: threading.Event) -> dict:
    """Puts the upload into dest. Returns {"kind": ..., "installer": "inno"|"nsis"|""}."""
    os.makedirs(dest, exist_ok=True)
    kind = sniff(src)
    name = os.path.basename(filename) or os.path.basename(src)
    info = {"kind": kind, "installer": ""}
    if kind == "zip":
        _unzip(src, dest, cancel)
    elif kind in ("tar", "zstd"):
        try:
            _untar(src, dest, cancel)
        except Exception as e:
            if isinstance(e, (Cancelled, InstallError)):
                raise
            if kind == "zstd" or "compression" in str(e).lower():
                _external(src, dest, "tar.zst", cancel)
                _check_tree(dest)
            else:
                raise InstallError(f"Couldn't unpack the archive: {e}") from None
    elif kind in ("7z", "rar"):
        _external(src, dest, kind, cancel)
        _check_tree(dest)
    elif kind in ("elf", "script", "pe"):
        out = os.path.join(dest, name)
        shutil.copyfile(src, out)
        if kind != "pe":
            os.chmod(out, 0o755)
        else:
            inst = windows_installer(out)
            info["installer"] = inst
            if inst:
                _try_extract_installer(out, dest, inst, cancel, info)
    elif kind == "msi":
        raise InstallError("This build is a Windows .msi installer, which isn't supported yet")
    elif kind in ("dmg", "apk"):
        raise InstallError(f"This is a {'macOS' if kind == 'dmg' else 'Android'} build")
    else:
        raise InstallError(f"Don't know how to install {name}")
    return info


def _try_extract_installer(exe: str, dest: str, inst: str, cancel: threading.Event, info: dict) -> None:
    """Inno Setup / NSIS installers can often be unpacked without running them. When that
    works the installer is removed; otherwise it stays and runs once through Proton."""
    out = os.path.join(dest, "game")
    try:
        if inst == "inno" and which("innoextract"):
            os.makedirs(out, exist_ok=True)
            _run([which("innoextract"), "-s", "-m", "-d", out, exe], "innoextract", cancel)
            app = os.path.join(out, "app")
            if os.path.isdir(app):
                out = app
        elif inst == "nsis" and which("7z", "7za", "7zz"):
            os.makedirs(out, exist_ok=True)
            _run([which("7z", "7za", "7zz"), "x", "-y", "-bd", f"-o{out}", exe], "7-Zip", cancel)
        else:
            return
        _check_tree(dest)
        if any(c["kind"] == "windows" for c in scan(out, "", [])[:1]):
            os.unlink(exe)
            info["installer"] = ""
            info["extracted"] = True
        else:
            rmtree(os.path.join(dest, "game"))
    except Cancelled:
        raise
    except Exception:
        rmtree(os.path.join(dest, "game"))


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


def _manifest_actions(root: str) -> list:
    """Actions from the developer's .itch.toml (https://itch.io/docs/itch/integrating/manifest.html)."""
    path = os.path.join(root, ".itch.toml")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            raw = f.read(65536)
        try:
            import tomllib  # type: ignore
            data = tomllib.loads(raw.decode("utf-8", "replace"))
            acts = data.get("actions") or []
        except ImportError:
            acts = []
            for block in re.split(r"\[\[actions\]\]", raw.decode("utf-8", "replace"))[1:]:
                a = dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"]*)"', block, re.M))
                acts.append(a)
        return [a for a in acts if isinstance(a, dict) and a.get("path")]
    except Exception:
        return []


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
            score += min(20.0, max(size, 1).bit_length() - 11)
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
    for a in _manifest_actions(root):
        rel = str(a.get("path", "")).replace("\\", "/")
        if re.match(r"^[a-z]+://", rel):
            continue
        plat = str(a.get("platform", "")).lower()
        for c in out:
            if c["path"].replace(os.sep, "/") == rel and (not plat or plat == c["kind"]):
                c["score"] += 1000
                args = a.get("args")
                if isinstance(args, list):
                    c["args"] = " ".join(f'"{x}"' if " " in str(x) else str(x) for x in args)
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


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
