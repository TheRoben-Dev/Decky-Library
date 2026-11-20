"""Ring RGB through Handheld Daemon.

HHD's Ally driver (hhd/device/rog_ally/base.py) registers these RGB modes:
  disabled: -
  solid:    color (hue, saturation, brightness)
  pulse:    color + speedd
  duality:  dual (hue, hue2, saturation, brightness) + speedd
  rainbow:  brightnessd
  spiral:   brightnessd, speedd, direction
The settings live under rgb.handheld.mode.* (hhd/plugins/rgb). HHD keeps the
choice in its own state and re-sends it after boot/suspend, so it persists
without this plugin.

The MCU's own "keep lighting during boot / while charging asleep" flags are
HHD options too (controllers.rog_ally.rgb_boot / rgb_charging). HHD sends them
with its documented config command; we never talk to the MCU ourselves.
"""
from . import hhd

MODES = ("off", "solid", "pulse", "duality", "rainbow", "spiral")
SPEEDS = ("low", "medium", "high")
BASE = "rgb.handheld.mode"


def _step(v, step, lo, hi):
    v = int(round(float(v) / step) * step)
    return max(lo, min(hi, v))


def _level(brightness: int) -> str:
    if brightness <= 33:
        return "low"
    if brightness <= 66:
        return "medium"
    return "high"


def to_state(light: dict) -> dict:
    """Plugin light spec -> HHD state keys. Values are clamped to HHD's ranges."""
    mode = light.get("mode", "solid")
    if mode not in MODES:
        mode = "solid"
    hue = _step(light.get("hue", 0), 5, 0, 360)
    hue2 = _step(light.get("hue2", 180), 5, 0, 360)
    sat = _step(light.get("saturation", 100), 10, 0, 100)
    bri = _step(light.get("brightness", 50), 10, 0, 100)
    speed = light.get("speed", "medium")
    speed = speed if speed in SPEEDS else "medium"
    direction = light.get("direction", "left")
    direction = direction if direction in ("left", "right") else "left"

    if mode == "off" or bri == 0:
        return {f"{BASE}.mode": "disabled"}
    out = {f"{BASE}.mode": mode}
    p = f"{BASE}.{mode}"
    if mode in ("solid", "pulse", "duality"):
        out.update({f"{p}.hue": hue, f"{p}.saturation": sat, f"{p}.brightness": bri})
    if mode == "duality":
        out[f"{p}.hue2"] = hue2
    if mode in ("pulse", "duality", "spiral"):
        out[f"{p}.speedd"] = speed
    if mode in ("rainbow", "spiral"):
        out[f"{p}.brightnessd"] = _level(bri)
    if mode == "spiral":
        out[f"{p}.direction"] = direction
    return out


def status(state: dict) -> dict:
    mode = state.get(f"{BASE}.mode")
    cmode = state.get("controllers.rog_ally.controller_mode.mode")
    led_passthrough = bool(state.get(f"controllers.rog_ally.controller_mode.{cmode}.led_support", False))
    return {
        "supported": mode is not None,
        "hhdRgbEnabled": bool(state.get("hhd.settings.rgb", False)),
        "mode": mode,
        "controllerOwnsLeds": cmode == "dualsense" and led_passthrough,
        "rgbBoot": bool(state.get("controllers.rog_ally.rgb_boot", False)),
        "rgbCharging": bool(state.get("controllers.rog_ally.rgb_charging", False)),
        "hasBootFlags": "controllers.rog_ally.rgb_boot" in state,
    }


def apply(light: dict, state: dict | None = None) -> bool:
    st = state if state is not None else hhd.get_state()
    vals = to_state(light)
    if not st.get("hhd.settings.rgb", True):
        # RGB support switched off in HHD: switch it on first, then the
        # rgb.* keys appear on HHD's next settings refresh.
        hhd.set_state({"hhd.settings.rgb": True})
        return True
    return hhd.set_changed(vals, st)


def set_flags(boot: bool, charging: bool) -> bool:
    return hhd.set_changed({
        "controllers.rog_ally.rgb_boot": bool(boot),
        "controllers.rog_ally.rgb_charging": bool(charging),
    })
