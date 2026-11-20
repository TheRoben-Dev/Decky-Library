"""Ring RGB through the kernel's LED class (no daemon needed).

Bazzite 44+ dropped Handheld Daemon for InputPlumber. There the rings are
driven by the kernel's hid-asus-ally driver, which registers a standard
multicolor LED (Documentation/leds/leds-class-multicolor.rst):

  /sys/class/leds/ally:rgb:joystick_rings/
      multi_index      colour layout, e.g. "rgb rgb rgb rgb" (4 zones, packed
                       0xRRGGBB) or "red green blue ..." (one value per channel)
      multi_intensity  one value per multi_index entry
      brightness       0..max_brightness (255), scales every channel
  /sys/class/leds/asus::kbd_backlight/brightness
                       the ring MCU's overall level (0..3) on the same device

InputPlumber reads the same LED (50-rog_ally.yaml, group
"led") and only writes to it when a game sends DualSense lightbar colours
to a DualSense target; the Ally's default target is Xbox Elite, so it leaves
the rings alone. The driver itself talks to the MCU; we never do.

Only static colours are offered here: the stock driver has no hardware
effects, and animating in software would mean a constant stream of HID writes.
"""
import colorsys
import os

LEDS = "/sys/class/leds"
SUFFIX = ":rgb:joystick_rings"
KBD = "asus::kbd_backlight"


def _read(p):
    try:
        with open(p) as f:
            return f.read().strip()
    except Exception:
        return None


def _write(p, v):
    with open(p, "w") as f:
        f.write(str(v))


def ring_path():
    try:
        for n in sorted(os.listdir(LEDS)):
            if n.endswith(SUFFIX) and os.path.exists(f"{LEDS}/{n}/multi_intensity"):
                return f"{LEDS}/{n}"
    except Exception:
        pass
    return None


def kbd_path(ring):
    """The ring MCU's level LED, only if it hangs off the same HID device."""
    p = f"{LEDS}/{KBD}"
    if not ring or not os.path.exists(f"{p}/brightness"):
        return None
    try:
        if os.path.dirname(os.path.realpath(p)) == os.path.dirname(os.path.realpath(ring)):
            return p
    except Exception:
        pass
    return None


def available() -> bool:
    return ring_path() is not None


def status() -> dict:
    ring = ring_path()
    if not ring:
        return {"supported": False}
    idx = (_read(f"{ring}/multi_index") or "").split()
    return {
        "supported": True,
        "name": os.path.basename(ring),
        "zones": max(1, sum(1 for t in idx if t in ("rgb", "multi", "blue"))),
        "layout": " ".join(idx),
    }


def _rgb(hue, sat):
    r, g, b = colorsys.hsv_to_rgb((int(hue) % 360) / 360, max(0, min(100, int(sat))) / 100, 1.0)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def to_values(light: dict, ring: str | None = None) -> dict | None:
    """Plugin light spec -> exact strings for the sysfs files (also what the
    boot/resume restore script writes)."""
    ring = ring or ring_path()
    if not ring:
        return None
    idx = (_read(f"{ring}/multi_index") or "").split()
    mx = int(_read(f"{ring}/max_brightness") or 255)
    mode = light.get("mode", "solid")
    pct = max(0, min(100, int(light.get("brightness", 50))))
    if mode == "off" or pct == 0:
        return {"intensity": None, "brightness": "0", "kbd": None}

    sat = light.get("saturation", 100)
    first = _rgb(light.get("hue", 0), sat)
    # Two-ring / two-colour modes: first half of the zones gets colour 1,
    # second half colour 2. Zone order is the driver's (assumed left ring
    # first; unverified on hardware).
    second = _rgb(light.get("hue2", 180), sat) if mode in ("split", "duality") else first

    zones = max(1, sum(1 for t in idx if t in ("rgb", "multi", "blue")))
    out, zone = [], 0
    for t in idx:
        col = first if zone < (zones + 1) // 2 or zones == 1 else second
        if t in ("rgb", "multi"):
            out.append(str((col[0] << 16) | (col[1] << 8) | col[2]))
            zone += 1
        elif t == "red":
            out.append(str(col[0]))
        elif t == "green":
            out.append(str(col[1]))
        elif t == "blue":
            out.append(str(col[2]))
            zone += 1
        else:  # white/amber/...: not used by the Ally driver; keep it dark
            out.append("0")
    kbd = kbd_path(ring)
    kmax = _read(f"{kbd}/max_brightness") if kbd else None
    return {
        "intensity": " ".join(out),
        "brightness": str(max(1, round(pct * mx / 100))),
        "kbd": kmax if kmax and kmax.isdigit() else None,
    }


def apply(light: dict) -> dict | None:
    ring = ring_path()
    vals = to_values(light, ring)
    if not vals:
        return None
    kbd = kbd_path(ring)
    if vals["kbd"] and kbd and _read(f"{kbd}/brightness") != vals["kbd"]:
        _write(f"{kbd}/brightness", vals["kbd"])
    if vals["intensity"] and _read(f"{ring}/multi_intensity") != vals["intensity"]:
        _write(f"{ring}/multi_intensity", vals["intensity"])
    # Always rewrite brightness: it's what makes the driver push the colour.
    _write(f"{ring}/brightness", vals["brightness"])
    return vals
