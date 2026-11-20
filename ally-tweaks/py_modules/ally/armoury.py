"""ASUS firmware toggles that Armoury Crate exposes on the Ally.

Only plain on/off WMI functions documented by the kernel are used:
  panel_overdrive  LCD response-time boost (less ghosting)
  boot_sound       BIOS POST sound
Newer kernels expose them through asus-armoury
(/sys/class/firmware-attributes/asus-armoury/attributes/<name>/current_value);
older ones through asus-nb-wmi (panel_od, boot_sound), see
Documentation/ABI/testing/sysfs-platform-asus-wmi.

Deliberately NOT exposed: mcu_powersave (HHD hides it by default because it can
leave the controller unresponsive after sleep), ppt_* / throttle_thermal_policy
/ fan curves (power and thermals stay at ASUS stock; TDP lives in Vex
Performance), and anything that isn't a documented attribute.
"""
import os

ARMOURY = "/sys/class/firmware-attributes/asus-armoury/attributes"
WMI = "/sys/devices/platform/asus-nb-wmi"
TOGGLES = {
    # plugin key: (asus-armoury name, legacy asus-nb-wmi name)
    "panelOverdrive": ("panel_overdrive", "panel_od"),
    "bootSound": ("boot_sound", "boot_sound"),
}


def _path(key):
    new, old = TOGGLES[key]
    p = f"{ARMOURY}/{new}/current_value"
    if os.path.exists(p):
        return p
    p = f"{WMI}/{old}"
    if os.path.exists(p):
        return p
    return None


def read_all() -> dict:
    out = {}
    for key in TOGGLES:
        p = _path(key)
        if not p:
            out[key] = None
            continue
        try:
            with open(p) as f:
                out[key] = f.read().strip() == "1"
        except Exception:
            out[key] = None
    return out


def write(key: str, on: bool) -> bool:
    if key not in TOGGLES:
        raise ValueError(f"unknown toggle {key}")
    p = _path(key)
    if not p:
        return False
    with open(p) as f:
        if (f.read().strip() == "1") == bool(on):
            return True
    with open(p, "w") as f:
        f.write("1" if on else "0")
    return True
