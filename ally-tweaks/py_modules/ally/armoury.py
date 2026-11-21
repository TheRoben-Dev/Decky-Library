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


# ---- GPU memory (UMA frame buffer), the "Memory assigned to GPU" option in
# Armoury Crate. asus-armoury apu_mem: value N = (N + 1) GB, 0 = Auto.
# Takes effect after a reboot (the kernel asks for one itself). It's a stock
# BIOS option; it only moves the RAM split between CPU and GPU.
APU_MEM = f"{ARMOURY}/apu_mem/current_value"
APU_CHOICES = [0, 1, 2, 3, 5, 7]   # Auto, 2, 3, 4, 6, 8 GB (Armoury Crate's set)


def apu_mem_status():
    if not os.path.exists(APU_MEM):
        return None
    try:
        with open(APU_MEM) as f:
            cur = int(f.read().strip())
    except Exception:
        cur = None
    return {"current": cur, "choices": APU_CHOICES}


def set_apu_mem(index: int) -> bool:
    index = int(index)
    if index not in APU_CHOICES or not os.path.exists(APU_MEM):
        return False
    with open(APU_MEM) as f:
        if f.read().strip() == str(index):
            return True
    with open(APU_MEM, "w") as f:
        f.write(str(index))
    return True
