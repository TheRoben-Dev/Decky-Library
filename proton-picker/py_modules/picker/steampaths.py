"""Locate the Steam install and every compatibilitytools.d folder Steam reads."""
import os

import decky

HOME = getattr(decky, "DECKY_USER_HOME", None) or os.path.expanduser("~")

_ROOT_CANDIDATES = [
    os.path.join(HOME, ".local/share/Steam"),     # native Steam (Bazzite, SteamOS)
    os.path.join(HOME, ".steam/root"),
    os.path.join(HOME, ".steam/steam"),
    os.path.join(HOME, ".var/app/com.valvesoftware.Steam/data/Steam"),  # flatpak
]

# System-wide tool folders Steam also scans. Distro packages live here; we
# list them but never write or delete in them.
SYSTEM_COMPAT_DIRS = [
    "/usr/share/steam/compatibilitytools.d",
    "/usr/local/share/steam/compatibilitytools.d",
]


def steam_root() -> str:
    for p in _ROOT_CANDIDATES:
        if os.path.isdir(os.path.join(p, "steamapps")) or os.path.isdir(os.path.join(p, "config")):
            return os.path.realpath(p)
    return os.path.realpath(_ROOT_CANDIDATES[0])


def user_compat_dir() -> str:
    """Where we install tools: <steam root>/compatibilitytools.d (same as ProtonPlus/ProtonUp-Qt)."""
    return os.path.join(steam_root(), "compatibilitytools.d")


def compat_dirs() -> list:
    seen, out = set(), []
    for p in [user_compat_dir(), *SYSTEM_COMPAT_DIRS]:
        rp = os.path.realpath(p)
        if rp not in seen and os.path.isdir(rp):
            seen.add(rp)
            out.append(rp)
    return out
