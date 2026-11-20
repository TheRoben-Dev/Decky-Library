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

Static colours (one, left/right, or four zones) work on every driver build.
Animated effects are offered only when the driver exposes the MCU's own
effects (effect/effect_index); the plugin never animates from software, which
would mean a constant stream of HID writes.
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
        "effects": hw_effects(ring),
    }


def hw_effects(ring=None):
    """Some hid-asus-ally builds expose the ring MCU's own effects as LED
    attributes (effect / effect_index / speed / direction). The MCU runs them
    itself, so nothing is animated from software. Empty list = not available."""
    ring = ring or ring_path()
    if not ring or not os.path.exists(f"{ring}/effect"):
        return []
    return (_read(f"{ring}/effect_index") or "").split()


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
    zones = max(1, sum(1 for t in idx if t in ("rgb", "multi", "blue")))
    hue, hue2 = light.get("hue", 0), light.get("hue2", 180)
    if mode == "zones":
        hues = list(light.get("zoneHues") or [hue] * 4)
        hues = (hues + [hue] * 4)[:4]
        sats = list(light.get("zoneSats") or [sat] * 4)
        sats = (sats + [sat] * 4)[:4]
        colors = [_rgb(hues[min(3, z * 4 // zones)], sats[min(3, z * 4 // zones)]) for z in range(zones)]
    elif mode in ("split", "duality"):
        # First half of the zones = colour 1, second half = colour 2. Zone
        # order is the driver's (assumed left ring first; unverified, and
        # swappable with "swapSides").
        a, b = _rgb(hue, sat), _rgb(hue2, sat)
        if light.get("swapSides"):
            a, b = b, a
        colors = [a if z < (zones + 1) // 2 or zones == 1 else b for z in range(zones)]
    else:
        colors = [_rgb(hue, sat)] * zones

    out, zone = [], 0
    for t in idx:
        col = colors[min(zone, zones - 1)]
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
    vals = {
        "intensity": " ".join(out),
        "brightness": str(max(1, round(pct * mx / 100))),
        "kbd": kmax if kmax and kmax.isdigit() else None,
    }
    eff = (light.get("hwEffect") or "") if mode == "hw" else ""
    effects = hw_effects(ring)
    if effects:
        # Static colour modes use the MCU's own "monocolor" effect so the
        # driver doesn't keep an old animation running.
        vals["effect"] = eff if eff in effects else ("monocolor" if "monocolor" in effects else None)
        if eff in effects:
            vals["speed"] = str(max(0, min(100, int(light.get("hwSpeed", 50)))))
    return vals


def readback(ring=None) -> dict:
    ring = ring or ring_path()
    if not ring:
        return {}
    return {"intensity": _read(f"{ring}/multi_intensity"), "brightness": _read(f"{ring}/brightness")}


def matches(vals: dict) -> bool:
    """True when the LED really shows what we set (catches driver resets after
    resume / re-probe, and other programs writing the LED)."""
    rb = readback()
    if not rb:
        return False
    if vals.get("intensity") is None:
        return rb.get("brightness") == "0"
    return rb.get("intensity") == vals["intensity"] and rb.get("brightness") == vals["brightness"]


def apply(light: dict) -> dict | None:
    ring = ring_path()
    vals = to_values(light, ring)
    if not vals:
        return None
    kbd = kbd_path(ring)
    if vals["kbd"] and kbd and _read(f"{kbd}/brightness") != vals["kbd"]:
        _write(f"{kbd}/brightness", vals["kbd"])
    if vals.get("effect") and _read(f"{ring}/effect") != vals["effect"]:
        try:
            _write(f"{ring}/effect", vals["effect"])
            if vals.get("speed") and os.path.exists(f"{ring}/speed"):
                _write(f"{ring}/speed", vals["speed"])
        except Exception:
            pass  # optional driver feature; colours below still apply
    if vals["intensity"] and _read(f"{ring}/multi_intensity") != vals["intensity"]:
        _write(f"{ring}/multi_intensity", vals["intensity"])
    # Always rewrite brightness: it's what makes the driver push the colour.
    _write(f"{ring}/brightness", vals["brightness"])
    return vals


# ---- who else writes the rings? ----
# InputPlumber copies a DualSense target's lightbar colour (sent by Steam or a
# game) onto this same LED. Steam's default DualSense lightbar is blue, so with
# a DualSense/DualShock target the rings get overwritten. Detect that so the UI
# can explain it instead of the plugin silently losing a tug-of-war.
import subprocess as _sp
import time as _time

_ip_cache = {"t": 0.0, "v": None}


def _busctl(*args):
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
    try:
        r = _sp.run(["busctl", "--system", *args], capture_output=True, text=True, timeout=5, env=env)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def inputplumber_lightbar_target():
    """Name of an InputPlumber target that forwards a lightbar (DualSense /
    DualShock), or None. Cached for 30 s."""
    now = _time.monotonic()
    if now - _ip_cache["t"] < 30:
        return _ip_cache["v"]
    found = None
    tree = _busctl("tree", "--list", "org.shadowblip.InputPlumber")
    for path in tree.split():
        if "/devices/target/" not in path or not path.rsplit("/", 1)[-1].startswith("gamepad"):
            continue
        out = _busctl("get-property", "org.shadowblip.InputPlumber", path, "org.shadowblip.Input.Gamepad", "Name")
        name = out.partition(" ")[2].strip().strip('"')
        if any(k in name.lower() for k in ("dualsense", "dualshock", "playstation")):
            found = name
            break
    _ip_cache.update(t=now, v=found)
    return found
