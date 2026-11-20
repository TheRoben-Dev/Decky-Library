"""Download, verify and unpack a Proton build into compatibilitytools.d.

Runs in a worker thread; the frontend polls `state()` for progress.
Unpacks into a hidden temp folder first and only moves the finished tool
into place, so a failed or interrupted install never leaves a half tool
that Steam would try to load.
"""
import hashlib
import os
import shutil
import tarfile
import tempfile
import threading
import time

import decky

from . import net, releases, steampaths, tools

_lock = threading.Lock()
_state: dict = {"phase": "idle"}


def state() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw):
    with _lock:
        _state.update(kw)


def busy() -> bool:
    return state().get("phase") in ("starting", "downloading", "verifying", "extracting")


def _safe_extract(tar: tarfile.TarFile, dest: str):
    if hasattr(tarfile, "data_filter"):
        tar.extractall(dest, filter="data")
        return
    root = os.path.realpath(dest)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == root or target.startswith(root + os.sep)):
            raise RuntimeError(f"unsafe path in archive: {m.name}")
        if m.issym() or m.islnk():
            link = os.path.realpath(os.path.join(os.path.dirname(target), m.linkname)) if m.issym() \
                else os.path.realpath(os.path.join(dest, m.linkname))
            if not (link == root or link.startswith(root + os.sep)):
                raise RuntimeError(f"unsafe link in archive: {m.name}")
        if m.isdev():
            raise RuntimeError(f"device node in archive: {m.name}")
    tar.extractall(dest)


def _run(family: str):
    tmpdir = None
    try:
        rel = releases.latest(family, force=True)
        asset = rel.get("asset")
        if not asset:
            raise RuntimeError(f"no installable asset in {rel.get('tag')}")
        compat = steampaths.user_compat_dir()
        os.makedirs(compat, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix=".proton-picker-", dir=compat)
        archive = os.path.join(tmpdir, asset["file"])
        total = int(asset.get("size") or 0)
        _set(phase="downloading", family=family, tag=rel["tag"], done_bytes=0, total=total, error=None)

        h = hashlib.sha512()
        with net.open_url(asset["url"], timeout=60) as r, open(archive, "wb") as f:
            total = int(r.headers.get("Content-Length") or total)
            got, last = 0, 0.0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if time.time() - last > 0.3:
                    _set(done_bytes=got, total=total)
                    last = time.time()
            _set(done_bytes=got, total=total)

        _set(phase="verifying")
        if asset.get("sha512_url"):
            expected = net.get_text(asset["sha512_url"]).split()[0].strip().lower()
            if h.hexdigest().lower() != expected:
                raise RuntimeError("checksum mismatch, download discarded")
            verified = True
        else:
            verified = False

        _set(phase="extracting")
        unpack = os.path.join(tmpdir, "x")
        os.makedirs(unpack)
        with tarfile.open(archive, "r:*") as t:
            _safe_extract(t, unpack)
        os.remove(archive)

        tops = [d for d in os.listdir(unpack) if os.path.isdir(os.path.join(unpack, d))]
        if len(tops) != 1:
            raise RuntimeError("unexpected archive layout")
        src = os.path.join(unpack, tops[0])
        info = tools.read_tool_dir(src)
        if not info:
            raise RuntimeError("archive has no compatibilitytool.vdf")
        dest = os.path.join(compat, tops[0])
        if os.path.exists(dest):
            existing = tools.read_tool_dir(dest)
            if existing and existing["name"] == info["name"]:
                _set(phase="done", tool=info["name"], display=info["display"], verified=verified, already=True)
                return
            raise RuntimeError(f"{tops[0]} already exists in compatibilitytools.d")
        with open(os.path.join(src, tools.OWNED_MARK), "w") as f:
            f.write(f"{family} {rel['tag']} installed {time.strftime('%Y-%m-%d')}\n")
        os.replace(src, dest)
        decky.logger.info(f"installed {info['name']} into {dest} (sha512 verified={verified})")
        _set(phase="done", tool=info["name"], display=info["display"], verified=verified, already=False)
    except Exception as e:
        decky.logger.error(f"install {family} failed: {e}")
        _set(phase="error", error=str(e))
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def start(family: str) -> dict:
    if family not in releases.SOURCES:
        return {"ok": False, "error": "unknown family"}
    with _lock:
        if _state.get("phase") in ("starting", "downloading", "verifying", "extracting"):
            return {"ok": False, "error": "another install is running"}
        _state.clear()
        _state.update(phase="starting", family=family)
    threading.Thread(target=_run, args=(family,), daemon=True).start()
    return {"ok": True}


def cleanup_stale():
    """Remove temp folders left by an install that was cut off (Steam/Decky restart)."""
    compat = steampaths.user_compat_dir()
    try:
        for e in os.listdir(compat):
            if e.startswith(".proton-picker-"):
                shutil.rmtree(os.path.join(compat, e), ignore_errors=True)
    except OSError:
        pass
