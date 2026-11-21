"""Discover installed compatibility tools from disk.

Steam itself is the source of truth for what it can *use* (the frontend asks
SteamClient.Apps.GetAvailableCompatTools). Disk scanning tells us what is
installed but not yet loaded (Steam only scans compatibilitytools.d at
startup) and which folders we may delete.
"""
import os
import re
import shutil

from . import steampaths, vdf

OWNED_MARK = ".proton-picker"


def family_of(name: str) -> str:
    n = name.lower()
    if "cachyos" in n:
        return "cachyos"
    if n.startswith("ge-proton") or "proton-ge" in n:
        return "ge"
    if "experimental" in n:
        return "experimental"
    if "hotfix" in n:
        return "hotfix"
    if n.startswith("proton"):
        return "valve"
    return "other"


def _version_key(name: str):
    return [int(x) for x in re.findall(r"\d+", name)]


def read_tool_dir(path: str):
    vdf_path = os.path.join(path, "compatibilitytool.vdf")
    if not os.path.isfile(vdf_path):
        return None
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
            data = vdf.loads(f.read())
    except Exception:
        return None
    tools = vdf.get_ci(data, "compatibilitytools", "compat_tools") or {}
    if not isinstance(tools, dict) or not tools:
        return None
    internal, info = next(iter(tools.items()))
    display = vdf.get_ci(info, "display_name") if isinstance(info, dict) else None
    return {
        "name": internal,
        "display": display or internal,
        "dir": path,
        "family": family_of(internal),
        "owned": os.path.exists(os.path.join(path, OWNED_MARK)),
        "system": os.path.dirname(os.path.realpath(path)) != os.path.realpath(steampaths.user_compat_dir()),
    }


def list_installed() -> list:
    out = []
    for base in steampaths.compat_dirs():
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue
        for e in entries:
            p = os.path.join(base, e)
            if e.startswith(".") or not os.path.isdir(p):
                continue
            t = read_tool_dir(p)
            if t:
                out.append(t)
    out.sort(key=lambda t: (t["family"], _version_key(t["name"])), reverse=True)
    return out


def remove(name: str) -> dict:
    """Delete a tool folder. Only user-folder tools; never system packages."""
    user_dir = steampaths.user_compat_dir()
    for t in list_installed():
        if t["name"] != name:
            continue
        if t["system"]:
            return {"ok": False, "error": "System-managed tool, not removing"}
        real = os.path.realpath(t["dir"])
        if os.path.dirname(real) != os.path.realpath(user_dir):
            return {"ok": False, "error": "Unexpected path, not removing"}
        shutil.rmtree(real)
        return {"ok": True}
    return {"ok": False, "error": "Tool not found"}
