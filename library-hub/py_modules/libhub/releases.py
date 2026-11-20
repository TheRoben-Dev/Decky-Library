"""Reads this repo's GitHub releases and downloads their assets with checksum checks.

Release convention (see .github/workflows/plugin-release.yml and nightgrid-release.yml):
tag `<id>-vX.Y.Z`, one `<Something>.zip` asset plus `<Something>.zip.sha256`. Plugin release
titles are "<plugin.json name> vX.Y.Z".

Trust model: only releases of OWNER/REPO, fetched over HTTPS with certificate checks from GitHub
hosts (see net.py). Asset URLs must point at that repo and that release's tag. A zip must match
the SHA-256 in its `.sha256` asset, and GitHub's own asset digest when the API reports one.
"""
import hashlib
import re

from . import net

OWNER = "TheRoben-Dev"
REPO = "Decky-Library"
RELEASES_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases?per_page=100"
DOWNLOAD_PREFIX = f"https://github.com/{OWNER}/{REPO}/releases/download/"

THEME_ID = "nightgrid-theme"
SELF_ID = "library-hub"
# Released once, now replaced by Library Hub: never offered for install.
RETIRED = {"nightgrid-updater"}
# Names used when a release title doesn't carry one (e.g. a release made by hand).
KNOWN_NAMES = {
    THEME_ID: "Nightgrid",
    SELF_ID: "Library Hub",
    "vex-performance": "Vex Performance",
    "proton-picker": "Proton Picker",
    "ally-tweaks": "Ally Tweaks",
}
MAX_ZIP = 30 * 1024 * 1024

_TAG = re.compile(r"^([a-z0-9][a-z0-9-]*?)-v(\d+)\.(\d+)\.(\d+)$")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_TITLE = re.compile(r"^(.+?)\s+v?\d+\.\d+\.\d+$")


def parse_version(v):
    m = _SEMVER.match((v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def fmt(ver) -> str:
    return "%d.%d.%d" % ver


def _name(rid: str, title: str) -> str:
    if rid in KNOWN_NAMES and rid in (THEME_ID, SELF_ID):
        return KNOWN_NAMES[rid]
    m = _TITLE.match((title or "").strip())
    if m and rid != THEME_ID:
        return m.group(1).strip()
    return KNOWN_NAMES.get(rid, rid)


def catalog(releases: list) -> dict:
    """{id: newest stable release item} for every `<id>-vX.Y.Z` release with a zip + .sha256."""
    best = {}
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        tag = r.get("tag_name", "")
        m = _TAG.match(tag)
        if not m:
            continue
        rid, ver = m.group(1), tuple(int(x) for x in m.groups()[1:])
        if rid in RETIRED:
            continue
        assets = {a.get("name"): a for a in r.get("assets", [])}
        zips = [n for n in assets if n and n.endswith(".zip") and n + ".sha256" in assets]
        if len(zips) != 1:
            continue
        if rid in best and best[rid]["_ver"] <= ver:
            pass
        elif rid in best:
            continue
        best[rid] = {
            "_ver": ver,
            "id": rid,
            "kind": "theme" if rid == THEME_ID else "plugin",
            "name": _name(rid, r.get("name", "")),
            "version": fmt(ver),
            "tag": tag,
            "url": r.get("html_url", ""),
            "notes": (r.get("body") or "")[:2000],
            "zip": assets[zips[0]],
            "sha": assets[zips[0] + ".sha256"],
        }
    return best


def fetch_catalog() -> dict:
    return catalog(net.get_json(RELEASES_URL))


def asset_url(asset: dict, tag: str) -> str:
    url = asset.get("browser_download_url", "")
    if not url.startswith(DOWNLOAD_PREFIX + tag + "/") or "/../" in url:
        raise ValueError(f"asset URL is not from {OWNER}/{REPO} release {tag}: {url}")
    return url


def expected_sha256(sha_text: str, zip_asset: dict) -> str:
    """Hash from the .sha256 file (`<hex>  Name.zip`); cross-checked with GitHub's digest."""
    m = re.match(r"^\s*([0-9a-fA-F]{64})\b", sha_text)
    if not m:
        raise ValueError("release .sha256 file is malformed")
    want = m.group(1).lower()
    digest = zip_asset.get("digest")
    if digest:
        if not digest.startswith("sha256:") or digest[7:].lower() != want:
            raise ValueError("release .sha256 file disagrees with GitHub's asset digest")
    return want


def download(item: dict):
    """Returns (zip bytes, sha256 hex), or raises if the checksum doesn't match."""
    tag = item["tag"]
    sha_text = net.fetch(asset_url(item["sha"], tag), 4096).decode("utf-8", "replace")
    want = expected_sha256(sha_text, item["zip"])
    data = net.fetch(asset_url(item["zip"], tag), MAX_ZIP)
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise ValueError(f"checksum mismatch (expected {want[:12]}…, got {got[:12]}…)")
    return data, want
