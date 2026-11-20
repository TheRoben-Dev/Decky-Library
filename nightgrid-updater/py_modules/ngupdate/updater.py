"""Finds the newest Nightgrid theme release on GitHub and installs it into CSS Loader's
themes folder.

Trust model: releases are only taken from one repository (REPO), over HTTPS with
certificate checks, from GitHub hosts only. The zip must match the SHA-256 published with
the release (the `.sha256` asset, and GitHub's own asset digest when the API reports it);
a mismatch aborts before anything on disk changes. The zip is then checked entry by entry
(only `Nightgrid/…`, no absolute paths, `..`, links or oversized files) before it's
extracted to a staging folder and swapped in, keeping CSS Loader's saved options
(config_*.json) and rolling back if the swap fails.
"""
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile

from . import net

OWNER = "TheRoben-Dev"
REPO = "Decky-Library"
TAG_PREFIX = "nightgrid-theme-v"
ASSET = "Nightgrid.zip"
THEME_DIR = "Nightgrid"
RELEASES_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases?per_page=50"
DOWNLOAD_PREFIX = f"https://github.com/{OWNER}/{REPO}/releases/download/"

MAX_ZIP = 15 * 1024 * 1024
MAX_UNPACKED = 40 * 1024 * 1024
MAX_ENTRIES = 500
MAX_MANIFEST = 9          # CSS Loader 2.1.x supports manifest_version up to 9

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(v):
    m = _SEMVER.match((v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def themes_dir(user_home: str) -> str:
    return os.path.join(user_home, "homebrew", "themes")


def installed_version(user_home: str):
    p = os.path.join(themes_dir(user_home), THEME_DIR, "theme.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("version")
    except FileNotFoundError:
        return None


def pick_release(releases: list):
    """Newest non-draft, non-prerelease `nightgrid-theme-vX.Y.Z` release with both assets."""
    best = None
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        tag = r.get("tag_name", "")
        if not tag.startswith(TAG_PREFIX):
            continue
        ver = parse_version(tag[len(TAG_PREFIX):])
        if not ver:
            continue
        assets = {a.get("name"): a for a in r.get("assets", [])}
        if ASSET not in assets or ASSET + ".sha256" not in assets:
            continue
        if best is None or ver > best[0]:
            best = (ver, r, assets)
    if not best:
        return None
    ver, r, assets = best
    return {
        "version": "v%d.%d.%d" % ver,
        "tag": r["tag_name"],
        "url": r.get("html_url", ""),
        "notes": (r.get("body") or "")[:2000],
        "zip": assets[ASSET],
        "sha": assets[ASSET + ".sha256"],
    }


def latest():
    return pick_release(net.get_json(RELEASES_URL))


def _asset_url(asset: dict, tag: str) -> str:
    url = asset.get("browser_download_url", "")
    if not url.startswith(DOWNLOAD_PREFIX + tag + "/"):
        raise ValueError(f"asset URL is not from {OWNER}/{REPO} release {tag}: {url}")
    return url


def expected_sha256(sha_text: str, zip_asset: dict) -> str:
    """Hash from the .sha256 file (`<hex>  Nightgrid.zip`); cross-checked with GitHub's
    asset digest when present."""
    m = re.match(r"^\s*([0-9a-fA-F]{64})\b", sha_text)
    if not m:
        raise ValueError("release .sha256 file is malformed")
    want = m.group(1).lower()
    digest = zip_asset.get("digest")
    if digest:
        if not digest.startswith("sha256:") or digest[7:].lower() != want:
            raise ValueError("release .sha256 file disagrees with GitHub's asset digest")
    return want


def verify_zip(data: bytes) -> dict:
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
                or parts[0] != THEME_DIR or ".." in parts):
            raise ValueError(f"unexpected path in zip: {name}")
        mode = i.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise ValueError(f"link in zip: {name}")
        total += i.file_size
        if total > MAX_UNPACKED:
            raise ValueError("zip unpacks too large")
    try:
        meta = json.loads(zf.read(f"{THEME_DIR}/theme.json").decode("utf-8"))
    except KeyError:
        raise ValueError("zip has no Nightgrid/theme.json")
    if meta.get("name") != THEME_DIR:
        raise ValueError("theme.json is not the Nightgrid theme")
    if int(meta.get("manifest_version", 1)) > MAX_MANIFEST:
        raise ValueError("theme needs a newer CSS Loader")
    return meta


def download(rel: dict):
    tag = rel["tag"]
    sha_text = net.fetch(_asset_url(rel["sha"], tag), 4096).decode("utf-8", "replace")
    want = expected_sha256(sha_text, rel["zip"])
    data = net.fetch(_asset_url(rel["zip"], tag), MAX_ZIP)
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise ValueError(f"checksum mismatch (expected {want[:12]}…, got {got[:12]}…)")
    return data


def install_zip(data: bytes, user_home: str, work_dir: str) -> str:
    """Extracts a verified zip and swaps it in for ~/homebrew/themes/Nightgrid."""
    meta = verify_zip(data)
    tdir = themes_dir(user_home)
    os.makedirs(tdir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    target = os.path.join(tdir, THEME_DIR)
    # Stage outside the themes folder so CSS Loader never sees a half-written theme.
    stage = tempfile.mkdtemp(prefix="stage-", dir=work_dir)
    backup = None
    try:
        zipfile.ZipFile(io.BytesIO(data)).extractall(stage)
        new = os.path.join(stage, THEME_DIR)
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
