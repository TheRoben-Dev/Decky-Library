"""lsfg-vk v2 integration: bundled layer install + per-game profiles, no launch options.

lsfg-vk 2.x is an implicit Vulkan layer that reads ~/.config/lsfg-vk/conf.toml
and activates a [[profile]] whose `active_in` lists the game's Steam AppID
(matched from the SteamAppId env var Steam already sets for every game).
So enabling frame gen for a game = adding a profile; disabling = removing it.
Changes take effect on the game's next launch.

We share conf.toml with the decky-lsfg-vk plugin: profiles we create are
tagged in our own state file, and we only delete profiles we own.
"""
import hashlib
import json
import os
import pwd
import re
import shutil
import tarfile
import tomllib

import decky

HOME = decky.DECKY_USER_HOME
CONF_DIR = os.path.join(HOME, ".config", "lsfg-vk")
CONF = os.path.join(CONF_DIR, "conf.toml")
OWNED = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "lsfg_owned.json")

LOCAL = os.path.join(HOME, ".local")
LAYER_JSON = "VkLayer_LSFGVK_frame_generation.json"
LAYER_CANDIDATES = [
    os.path.join(LOCAL, "share/vulkan/implicit_layer.d", LAYER_JSON),
    "/usr/share/vulkan/implicit_layer.d/" + LAYER_JSON,
    "/etc/vulkan/implicit_layer.d/" + LAYER_JSON,
]
LEGACY_LAYER = os.path.join(LOCAL, "share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json")

# Official, unmodified lsfg-vk build shipped inside the plugin zip (bin/).
# lsfg-vk is CC BY-NC-ND 4.0: verbatim, non-commercial redistribution with
# attribution. We never modify it; we only extract it into ~/.local.
BUNDLED_VERSION = "2.0.0"
BUNDLED_ARCHIVE = os.path.join(decky.DECKY_PLUGIN_DIR, "bin", f"lsfg-vk-{BUNDLED_VERSION}.tar.xz")
BUNDLED_SHA256 = "08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74"
PAYLOAD = {  # archive path -> (destination under ~/.local, mode)
    "bin/lsfg-vk-cli": ("bin/lsfg-vk-cli", 0o755),
    "lib/liblsfg-vk-layer.so": ("lib/liblsfg-vk-layer.so", 0o644),
    "lib/liblsfg-vk-layer.x86.so": ("lib/liblsfg-vk-layer.x86.so", 0o644),
    "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json":
        ("share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json", 0o644),
    "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.x86.json":
        ("share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.x86.json", 0o644),
}
INSTALL_STATE = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "lsfg_install.json")
OTHER_PLUGIN_DIRS = ["decky-lsfg-vk", "Decky LSFG-VK", "lsfg-vk"]
LS_APPID = "993090"
LS_BRANCH = "lsfg-vk"


# ---------------- Lossless Scaling (Steam app 993090) detection ----------------
def _steam_libraries():
    seen, out = set(), []
    roots = [os.path.join(HOME, p) for p in (".local/share/Steam", ".steam/steam", ".steam/root",
                                             ".var/app/com.valvesoftware.Steam/.local/share/Steam")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        cands = [root]
        for vdf in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf"):
            try:
                with open(os.path.join(root, vdf), encoding="utf-8", errors="replace") as f:
                    cands += [m.replace("\\\\", "\\") for m in re.findall(r'(?m)^\s*"path"\s+"([^"]*)"', f.read())]
            except OSError:
                pass
        for c in cands:
            real = os.path.realpath(c)
            if real not in seen and os.path.isdir(c):
                seen.add(real)
                out.append(c)
    return out


def lossless_status():
    info = {"installed": False, "branch": None, "needsBranch": True, "dll": ""}
    for lib in _steam_libraries():
        d = os.path.join(lib, "steamapps/common/Lossless Scaling")
        manifest = os.path.join(lib, f"steamapps/appmanifest_{LS_APPID}.acf")
        if not os.path.isdir(d) and not os.path.isfile(manifest):
            continue
        info["installed"] = True
        try:
            with open(manifest, encoding="utf-8", errors="replace") as f:
                text = f.read()
            m = re.search(r'"UserConfig"\s*\{[^}]*?"BetaKey"\s+"([^"]*)"', text, re.S)
            info["branch"] = m.group(1) if m and m.group(1) else "public"
        except OSError:
            pass
        dll = os.path.join(d, "lsfg-vk.dll")
        if os.path.isfile(dll):
            info["dll"] = dll
        info["needsBranch"] = info["branch"] != LS_BRANCH and not info["dll"]
        break
    return info


# ---------------- bundled layer install ----------------
def _install_state():
    try:
        with open(INSTALL_STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def other_plugin():
    base = os.path.join(HOME, "homebrew", "plugins")
    for name in OTHER_PLUGIN_DIRS:
        if os.path.isdir(os.path.join(base, name)):
            return name
    return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install_layer(force=False):
    """Extract the bundled lsfg-vk into ~/.local. Leaves an existing install
    from the Decky LSFG-VK plugin (or a distro package) alone unless forced."""
    current = next((p for p in LAYER_CANDIDATES if os.path.exists(p)), None)
    owned = _install_state().get("files")
    if current and not owned and not force:
        return {"ok": True, "skipped": "lsfg-vk is already installed by something else; using it"}
    if not os.path.isfile(BUNDLED_ARCHIVE):
        return {"ok": False, "error": "bundled lsfg-vk archive missing from the plugin"}
    if _sha256(BUNDLED_ARCHIVE) != BUNDLED_SHA256:
        return {"ok": False, "error": "bundled lsfg-vk archive failed its checksum"}
    ids = _user_ids()
    written = []
    with tarfile.open(BUNDLED_ARCHIVE, "r:xz") as tar:
        members = {m.name.removeprefix("./"): m for m in tar.getmembers() if m.isfile()}
        missing = [k for k in PAYLOAD if k not in members]
        if missing:
            return {"ok": False, "error": "archive missing " + ", ".join(missing)}
        for src, (rel, mode) in PAYLOAD.items():
            dest = os.path.join(LOCAL, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".vex.tmp"
            with tar.extractfile(members[src]) as fin, open(tmp, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            os.chmod(tmp, mode)
            if ids:
                os.chown(tmp, *ids)
            os.replace(tmp, dest)
            written.append(dest)
    if ids:  # dirs we may have created
        for d in {os.path.dirname(p) for p in written}:
            while d.startswith(LOCAL) and d != HOME:
                try:
                    os.chown(d, *ids)
                except OSError:
                    pass
                d = os.path.dirname(d)
    os.makedirs(os.path.dirname(INSTALL_STATE), exist_ok=True)
    with open(INSTALL_STATE, "w") as f:
        json.dump({"version": BUNDLED_VERSION, "files": written}, f)
    _ensure_config()
    return {"ok": True, "installed": BUNDLED_VERSION}


def uninstall_layer():
    st = _install_state()
    if other_plugin():  # the LSFG-VK plugin may have taken these files over
        return
    for p in st.get("files", []):
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.remove(INSTALL_STATE)
    except OSError:
        pass


def _ensure_config():
    data = _read()
    if data is None:
        data = _base()
    elif data.get("version") != 2:
        return
    ls = lossless_status()
    if ls["dll"] and data.setdefault("global", {}).get("dll") != ls["dll"]:
        data["global"]["dll"] = ls["dll"]
    if not data.get("profile"):
        data["profile"] = _base()["profile"]
    _write(data)


def _toml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[ " + ", ".join(_toml_val(x) for x in v) + " ]"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _dump(data: dict) -> str:
    """Writer for the flat lsfg-vk v2 schema: scalars, [global], [[profile]].
    Unknown keys are preserved."""
    lines = []
    for k, v in data.items():
        if not isinstance(v, (dict, list)) or (isinstance(v, list) and not (v and isinstance(v[0], dict))):
            lines.append(f"{k} = {_toml_val(v)}")
    for k, v in data.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]"] + [f"{a} = {_toml_val(b)}" for a, b in v.items()]
    for k, v in data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            for item in v:
                lines += ["", f"[[{k}]]"] + [f"{a} = {_toml_val(b)}" for a, b in item.items()]
    return "\n".join(lines) + "\n"


def _user_ids():
    try:
        pw = pwd.getpwnam(decky.DECKY_USER)
        return pw.pw_uid, pw.pw_gid
    except Exception:
        return None


def _read():
    if not os.path.exists(CONF):
        return None
    with open(CONF, "rb") as f:
        return tomllib.load(f)


def _write(data: dict):
    os.makedirs(CONF_DIR, exist_ok=True)
    text = _dump(data)
    tomllib.loads(text)  # sanity-check our own output before replacing the file
    tmp = CONF + ".vex.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    ids = _user_ids()
    if ids:
        os.chown(tmp, *ids)
        try:
            os.chown(CONF_DIR, *ids)
        except Exception:
            pass
    os.chmod(tmp, 0o644)
    os.replace(tmp, CONF)


def _owned():
    try:
        with open(OWNED) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_owned(s):
    os.makedirs(os.path.dirname(OWNED), exist_ok=True)
    with open(OWNED, "w") as f:
        json.dump(sorted(s), f)


def _find_dll():
    return lossless_status()["dll"]


def status():
    layer = next((p for p in LAYER_CANDIDATES if os.path.exists(p)), None)
    st = _install_state()
    info = {
        "installed": bool(layer),
        "ownedByVex": bool(st.get("files")),
        "otherPlugin": other_plugin(),
        "bundled": os.path.isfile(BUNDLED_ARCHIVE),
        "bundledVersion": BUNDLED_VERSION,
        "legacyV1": os.path.exists(LEGACY_LAYER) and not layer,
        "configExists": os.path.exists(CONF),
        "dll": "",
        "dllFound": False,
        "version": None,
        "lossless": lossless_status(),
    }
    info["dllFound"] = bool(info["lossless"]["dll"])
    try:
        data = _read()
        if data:
            info["version"] = data.get("version")
            info["dll"] = (data.get("global") or {}).get("dll", "")
    except Exception as e:
        info["error"] = f"conf.toml unreadable: {e}"
    return info


def _base():
    return {"version": 2, "global": {"allow_fp16": True}, "profile": [
        {"name": "", "pacing_mode": "vsync", "multiplier": 2, "flow_scale": 0.8,
         "performance_mode": False, "override_present_mode": True,
         "preserve_swapchain_image_count": False}]}


def set_game(appid: str, name: str, enabled: bool, multiplier: int, flow_scale: float, perf: bool):
    if enabled and not any(os.path.exists(p) for p in LAYER_CANDIDATES):
        res = install_layer()
        if not res.get("ok"):
            return res
    data = _read()
    if data is None:
        if not enabled:
            return {"ok": True}
        data = _base()
    if data.get("version") != 2:
        return {"ok": False, "error": "conf.toml is not lsfg-vk v2 format; update lsfg-vk first"}
    data.setdefault("global", {})
    dll = _find_dll()
    if dll:
        data["global"]["dll"] = dll
    profiles = data.get("profile") or []
    owned = _owned()

    existing = next((p for p in profiles if appid in [str(x) for x in p.get("active_in", [])]), None)
    if enabled:
        if existing is None:
            pname = f"{name} ({appid})" if any(p.get("name") == name for p in profiles) else name
            existing = {"name": pname, "active_in": [appid], "pacing_mode": "vsync"}
            profiles.append(existing)
            owned.add(pname)
        existing["multiplier"] = max(2, min(4, int(multiplier)))
        existing["flow_scale"] = round(max(0.25, min(1.0, float(flow_scale))), 2)
        existing["performance_mode"] = bool(perf)
        existing.setdefault("pacing_mode", "vsync")
        existing.setdefault("override_present_mode", True)
        existing.setdefault("preserve_swapchain_image_count", False)
    elif existing is not None:
        existing["active_in"] = [x for x in existing.get("active_in", []) if str(x) != appid]
        if not existing["active_in"] and existing.get("name") in owned:
            profiles.remove(existing)
            owned.discard(existing.get("name"))
    # lsfg-vk wants at least one profile table to exist
    if not profiles:
        profiles = _base()["profile"]
    data["profile"] = profiles
    _write(data)
    _save_owned(owned)
    return {"ok": True, "dll": data["global"].get("dll", "")}


def remove_all_owned():
    data = _read()
    owned = _owned()
    if not data or not owned:
        return
    data["profile"] = [p for p in data.get("profile", []) if p.get("name") not in owned] or _base()["profile"]
    _write(data)
    _save_owned(set())
