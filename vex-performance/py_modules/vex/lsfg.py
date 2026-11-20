"""lsfg-vk v2 integration without launch options.

lsfg-vk 2.x is an implicit Vulkan layer that reads ~/.config/lsfg-vk/conf.toml
and activates a [[profile]] whose `active_in` lists the game's Steam AppID
(matched from the SteamAppId env var Steam already sets for every game).
So enabling frame gen for a game = adding a profile; disabling = removing it.
Changes take effect on the game's next launch.

We share conf.toml with the decky-lsfg-vk plugin: profiles we create are
tagged in our own state file, and we only delete profiles we own.
"""
import json
import os
import pwd
import tomllib

import decky

HOME = decky.DECKY_USER_HOME
CONF_DIR = os.path.join(HOME, ".config", "lsfg-vk")
CONF = os.path.join(CONF_DIR, "conf.toml")
OWNED = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "lsfg_owned.json")

LAYER_CANDIDATES = [
    os.path.join(HOME, ".local/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json"),
    "/usr/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json",
    "/etc/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json",
]
LEGACY_LAYER = os.path.join(HOME, ".local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json")
DLL_GUESSES = [
    os.path.join(HOME, ".local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"),
    os.path.join(HOME, ".steam/steam/steamapps/common/Lossless Scaling/Lossless.dll"),
]


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
    for p in DLL_GUESSES:
        if os.path.exists(p):
            return p
    return ""


def status():
    layer = next((p for p in LAYER_CANDIDATES if os.path.exists(p)), None)
    flatpak = os.path.isdir("/var/lib/flatpak/runtime/org.freedesktop.Platform.VulkanLayer.lsfgvk") or \
        os.path.isdir(os.path.join(HOME, ".local/share/flatpak/runtime/org.freedesktop.Platform.VulkanLayer.lsfgvk"))
    info = {
        "installed": bool(layer),
        "legacyV1": os.path.exists(LEGACY_LAYER) and not layer,
        "flatpakLayer": flatpak,
        "configExists": os.path.exists(CONF),
        "dll": "",
        "dllFound": bool(_find_dll()),
        "version": None,
    }
    try:
        data = _read()
        if data:
            info["version"] = data.get("version")
            info["dll"] = (data.get("global") or {}).get("dll", "")
    except Exception as e:
        info["error"] = f"conf.toml unreadable: {e}"
    return info


def _base():
    return {"version": 2, "global": {"allow_fp16": True}, "profile": []}


def set_game(appid: str, name: str, enabled: bool, multiplier: int, flow_scale: float, perf: bool):
    data = _read()
    if data is None:
        if not enabled:
            return {"ok": True}
        data = _base()
    if data.get("version") != 2:
        return {"ok": False, "error": "conf.toml is not lsfg-vk v2 format; update lsfg-vk first"}
    data.setdefault("global", {})
    if not data["global"].get("dll"):
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
        profiles = [{"name": "", "pacing_mode": "vsync", "multiplier": 2, "flow_scale": 0.8,
                     "performance_mode": False, "override_present_mode": True,
                     "preserve_swapchain_image_count": False}]
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
