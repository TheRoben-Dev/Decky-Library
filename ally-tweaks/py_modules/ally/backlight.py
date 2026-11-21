"""Read-only screen backlight (Documentation/ABI/stable/sysfs-class-backlight).

actual_brightness is what the hardware is really at (it follows gamescope's
brightness slider and its idle dimming); brightness is the requested value and
is the fallback. bl_power != 0 means the panel backlight is powered off.
On the Ally this is the amdgpu_bl* device of the internal eDP panel.
"""
import os

BL = "/sys/class/backlight"


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def device():
    try:
        names = sorted(os.listdir(BL))
    except Exception:
        return None
    # Prefer the GPU's own (raw) backlight, which is the Ally's panel.
    for pref in ("amdgpu_bl", ""):
        for n in names:
            if n.startswith(pref) and _read_int(f"{BL}/{n}/max_brightness"):
                return f"{BL}/{n}"
    return None


def fraction():
    """0.0-1.0 of the panel's real backlight level, 0.0 when it is off, or None."""
    d = device()
    if not d:
        return None
    mx = _read_int(f"{d}/max_brightness")
    if not mx:
        return None
    power = _read_int(f"{d}/bl_power")
    if power not in (None, 0):
        return 0.0
    cur = _read_int(f"{d}/actual_brightness")
    if cur is None:
        cur = _read_int(f"{d}/brightness")
    if cur is None:
        return None
    return max(0.0, min(1.0, cur / mx))
