"""Installs a verified theme zip (Nightgrid, Lowpoly, …) into CSS Loader's themes folder.

Every function takes the theme's folder name (= its theme.json "name", releases.THEMES).
The zip has already passed the release checksum (releases.download). It's then checked entry by entry
(only `<Folder>/…`, no absolute paths, `..`, links or oversized files) before it's
extracted to a staging folder and swapped in, keeping CSS Loader's saved options
(config_*.json) and rolling back if the swap fails.
"""
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile


THEME_DIR = "Nightgrid"   # default folder, kept for callers that predate multiple themes

MAX_UNPACKED = 40 * 1024 * 1024
MAX_ENTRIES = 500
MAX_MANIFEST = 9          # CSS Loader 2.1.x supports manifest_version up to 9



def themes_dir(user_home: str) -> str:
    return os.path.join(user_home, "homebrew", "themes")


def installed_version(user_home: str, folder: str = THEME_DIR):
    p = os.path.join(themes_dir(user_home), folder, "theme.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            v = json.load(f).get("version")
            return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def verify_zip(data: bytes, folder: str = THEME_DIR) -> dict:
    """Validates every entry and returns the packaged theme.json."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if not infos or len(infos) > MAX_ENTRIES:
        raise ValueError("zip is empty or has too many entries")
    total = 0
    for i in infos:
        name = i.filename
        parts = name.split("/")
        if (name.startswith("/") or "\\" in name or ":" in parts[0]
                or parts[0] != folder or ".." in parts):
            raise ValueError(f"unexpected path in zip: {name}")
        mode = i.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise ValueError(f"link in zip: {name}")
        total += i.file_size
        if total > MAX_UNPACKED:
            raise ValueError("zip unpacks too large")
    try:
        meta = json.loads(zf.read(f"{folder}/theme.json").decode("utf-8"))
    except KeyError:
        raise ValueError(f"zip has no {folder}/theme.json")
    if meta.get("name") != folder:
        raise ValueError(f"theme.json is not the {folder} theme")
    if int(meta.get("manifest_version", 1)) > MAX_MANIFEST:
        raise ValueError("theme needs a newer CSS Loader")
    return meta


def install_zip(data: bytes, user_home: str, work_dir: str, folder: str = THEME_DIR) -> str:
    """Extracts a verified zip and swaps it in for ~/homebrew/themes/<folder>."""
    meta = verify_zip(data, folder)
    tdir = themes_dir(user_home)
    os.makedirs(tdir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    if not os.access(tdir, os.W_OK):
        raise PermissionError(f"{tdir} isn't writable by this user (CSS Loader may have created it as root). "
                              f"Fix once in Desktop Mode: sudo chown -R $USER: ~/homebrew/themes")
    target = os.path.join(tdir, folder)
    # Stage outside the themes folder so CSS Loader never sees a half-written theme.
    stage = tempfile.mkdtemp(prefix="stage-", dir=work_dir)
    backup = None
    try:
        zipfile.ZipFile(io.BytesIO(data)).extractall(stage)
        new = os.path.join(stage, folder)
        if os.path.isdir(target):
            for f in os.listdir(target):        # CSS Loader's saved on/off state + options
                if re.fullmatch(r"config_[A-Za-z]+\.json", f):
                    shutil.copy2(os.path.join(target, f), os.path.join(new, f))
            backup = os.path.join(work_dir, "backup-%d" % int(time.time()))
            shutil.move(target, backup)
        try:
            shutil.move(new, target)
        except Exception:
            if backup and not os.path.exists(target):
                shutil.move(backup, target)
                backup = None
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
    return meta.get("version", "")


def uninstall(user_home: str, work_dir: str, folder: str = THEME_DIR) -> bool:
    """Removes ~/homebrew/themes/<folder> (moved aside first, so a failure leaves it intact)."""
    target = os.path.join(themes_dir(user_home), folder)
    if not os.path.isdir(target):
        return False
    os.makedirs(work_dir, exist_ok=True)
    trash = os.path.join(work_dir, "removed-%d" % int(time.time()))
    shutil.move(target, trash)
    shutil.rmtree(trash, ignore_errors=True)
    return True
