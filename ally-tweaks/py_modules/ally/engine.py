"""Background logic: picks the ring lighting for the current moment, handles
per-game back-button layouts and the one-shot "full charge" switch.

Runs inside the Decky backend, so it keeps working with the Quick Access menu
closed. Everything it sets lives in Handheld Daemon or the kernel, so the last
lighting / charge limit / button setup stays in place if Decky stops; only the
*changing* parts (battery/temperature colours, low-battery pulse, per-game
switching) need the plugin running.
"""
import copy
import threading
import time

import decky

from . import backlight, battery, buttons, hhd, leds, rgb, sensors, settings, tweaks
from .persist import Persist

DEFAULTS = {
    "rgb": {
        "managed": True,
        "base": {"mode": "solid", "hue": 200, "hue2": 300, "saturation": 100,
                 "brightness": 50, "speed": "medium", "direction": "left"},
        "reactive": "none",          # none | battery | temperature | tdp
        "lowBattery": True,
        "lowBatteryAt": 15,
        "offOnBattery": False,
        "followScreen": False,       # scale ring brightness with the panel backlight
        "perGame": {},               # appid -> {"name", "light"}
    },
    "charge": {"limit": 100, "travel": False},
    "buttons": {"perGame": {}, "default": None},  # appid -> {"name", "paddles", "nintendo"}
    "panel": {},                     # desired armoury toggles, only keys the user changed
    "system": {
        "wifiPowersaveOff": False, "usbAutosuspendOff": False,
        "cpuBoostOff": False, "smtOff": False, "epp": "",      # "" = follow power profile
        "audioPowersaveOff": False, "splitLockMitigation": False, "ampsAwake": False,
        "touch": "on",                                          # on | off | games
    },
}

SYSTEM_KEYS = ("wifiPowersaveOff", "usbAutosuspendOff", "cpuBoostOff", "smtOff",
               "audioPowersaveOff", "splitLockMitigation", "ampsAwake")

# Colours that match HHD's own TDP-mode flash (hhd/plugins/rgb/__init__.py)
TDP_COLORS = {
    "quiet": (240, 100),
    "balanced": (0, 0),       # white
    "performance": (0, 100),
    "custom": (280, 100),
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("perGame",):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.conf = _merge(DEFAULTS, settings.load())
        self.game = None            # {"appid", "name"}
        self.last_light = None
        self.last_ac = None
        self.reason = ""
        self.temp_bin = None
        self.persist = Persist()
        self.readback_ok = False
        self.drifts = []
        self.led_contested = False
        self.sys_errors = {}
        self.last_hid = 0.0        # tweak key -> last apply error
        self.screen = None          # debounced backlight fraction
        self._screen_seen = None

    # ---------- settings ----------
    def save(self):
        settings.save(self.conf)

    def update(self, patch: dict):
        with self.lock:
            self.conf = _merge(self.conf, patch)
            self.save()
        self.tick(force=True)

    # ---------- lighting ----------
    def _scaled(self, light: dict) -> dict:
        """Follow screen brightness: ring brightness = your chosen brightness x
        the panel's real backlight level, in 1 % steps. Never drops below 3 %
        while the screen is on; off when the panel backlight is off."""
        if not self.conf["rgb"].get("followScreen") or light.get("mode") == "off":
            return light
        f = self.screen
        if f is None:
            return light
        if f <= 0:
            return {"mode": "off"}
        out = dict(light)
        b = int(light.get("brightness", 50)) * f
        out["brightness"] = max(3, min(100, int(round(b))))
        return out

    def _target(self, snap: dict, state: dict | None):
        return self._scaled(self._pick(snap, state))

    def _pick(self, snap: dict, state: dict | None):
        r = self.conf["rgb"]
        base = r["base"]
        on_battery = snap.get("present") and not snap.get("ac")
        cap = snap.get("capacity")

        if r["lowBattery"] and on_battery and cap is not None and cap <= int(r["lowBatteryAt"]):
            self.reason = f"Low battery ({cap}%)"
            return {"mode": "pulse", "hue": 0, "saturation": 100,
                    "brightness": max(50, int(base.get("brightness", 50))), "speed": "medium"}
        if r["offOnBattery"] and on_battery:
            self.reason = "Off on battery"
            return {"mode": "off"}

        appid = (self.game or {}).get("appid")
        game = r["perGame"].get(appid) if appid else None
        if game:
            self.reason = f"Game: {game.get('name', appid)}"
            return game["light"]

        mode = r["reactive"]
        if mode == "none" or base.get("mode") in ("off", "rainbow", "spiral"):
            self.reason = "Default"
            return base
        light = dict(base)
        if light["mode"] == "duality":
            light["mode"] = "solid"
        if mode == "battery" and cap is not None:
            light["hue"] = round(cap / 10) * 12           # 0% red -> 100% green
            light["saturation"] = 100
            self.reason = f"Battery {cap}%"
        elif mode == "temperature":
            t = sensors.apu_temp()
            if t is not None:
                # 5 °C steps with hysteresis so the colour (and HHD's saved
                # state) doesn't flap when the APU sits on a boundary.
                prev = self.temp_bin
                if prev is None or abs(t - prev) >= 5:
                    self.temp_bin = max(40, min(90, round(t / 5) * 5))
                t = self.temp_bin
                light["hue"] = 200 - (t - 40) * 4         # cyan 40°C -> red 90°C
                light["saturation"] = 100
                self.reason = f"APU {t}°C"
        elif mode == "tdp" and state is not None:
            m = None
            for k, v in state.items():
                if k.startswith("tdp.") and k.endswith(".tdp_v2.mode"):
                    m = v
                    break
            if m in TDP_COLORS:
                light["hue"], light["saturation"] = TDP_COLORS[m]
                self.reason = f"TDP mode: {m}"
        return light

    def rgb_backend(self, state: dict | None = None) -> str:
        """'hhd' when Handheld Daemon is running and owns the rings (older
        Bazzite, other distros), else 'sysfs' (kernel LED class, Bazzite 44+
        with InputPlumber), else 'none'."""
        if hhd.available():
            try:
                st = state if state is not None else hhd.get_state()
                if "hhd.settings.rgb" in st:
                    return "hhd"
            except Exception:
                pass
        return "sysfs" if leds.available() else "none"

    def _apply_light(self, target, state, force):
        be = self.rgb_backend(state)
        if be == "hhd":
            key = ("hhd", tuple(sorted(rgb.to_state(target).items())))
            if force or key != self.last_light:
                rgb.apply(target, state)
                self.last_light = key
        elif be == "sysfs" and leds.use_hid():
            # Kernel clamps packed colours (everything turns blue): send the
            # MCU's own LED report. No readback exists, so re-send on change,
            # on force (resume / settings) and every 10 s, which also wins back
            # the rings after something writes the LED class (the driver then
            # pushes its clamped blue).
            vals = leds.to_values(target)
            key = ("hid", (vals or {}).get("hid"))
            now = time.monotonic()
            if force or key != self.last_light or now - self.last_hid > 10:
                leds.apply_hid(target)
                self.last_light = key
                self.last_hid = now
                self.led_contested = False
                if vals:
                    # Restore unit sends the same report at boot / after resume;
                    # drop the LED-class values, which would only push blue.
                    self.persist.update(RGB_HID=vals["hid"], RGB_INTENSITY=None,
                                        RGB_BRIGHTNESS=None, KBD_LEVEL=None)
        elif be == "sysfs":
            vals = leds.to_values(target)
            key = ("sysfs", tuple(sorted((vals or {}).items())))
            # Re-assert when the LED doesn't show what we set: the driver can
            # reset it after resume or re-probe, or another program wrote it.
            if vals and not force and key == self.last_light and self.readback_ok and not leds.matches(vals):
                now = time.monotonic()
                self.drifts = [t for t in self.drifts if now - t < 120] + [now]
                if len(self.drifts) >= 3:
                    # Something keeps overwriting the rings (usually Steam's
                    # DualSense lightbar via InputPlumber). Don't fight it every
                    # few seconds; the UI explains it. User changes still apply.
                    if not self.led_contested:
                        decky.logger.warning("Ring LED keeps being overwritten by another program; not re-asserting")
                    self.led_contested = True
                else:
                    decky.logger.info("Ring LED drifted from the set colour; re-applying")
                    force = True
            if key != self.last_light:
                self.led_contested = False
                self.drifts = []
            if force or key != self.last_light:
                leds.apply(target)
                self.last_light = key
                # If this driver reports values in another format, a readback
                # never matches; don't keep rewriting the LED because of that.
                self.readback_ok = bool(vals) and leds.matches(vals)
                # Same values come back at boot / after resume via the unit.
                if not vals:
                    return
                self.persist.update(RGB_HID=None, RGB_INTENSITY=vals.get("intensity"),
                                    RGB_BRIGHTNESS=vals.get("brightness"),
                                    KBD_LEVEL=vals.get("kbd"))

    # ---------- system tweaks ----------
    def set_system(self, key: str, on):
        """on is a bool, except for "epp" (a preference name or "" for default)
        and "touch". The choice is saved first, so it sticks even if applying
        it fails; a failure is kept per tweak and shown under its toggle, and
        the periodic tick / restore unit keep trying."""
        if key == "touch":
            on = on if on in ("on", "off", "games") else "on"
        elif key == "epp":
            on = on if on in tweaks.EPP_VALUES else ""
        elif key in SYSTEM_KEYS:
            on = bool(on)
        else:
            raise ValueError(f"unknown tweak {key}")
        with self.lock:
            self.conf["system"][key] = on
            self.save()
            try:
                self._apply_system_key(key, on)
                self.sys_errors.pop(key, None)
            except Exception as e:
                msg = str(e) or e.__class__.__name__
                self.sys_errors[key] = msg
                decky.logger.error(f"applying {key}={on} failed: {msg}")
                raise

    def _apply_system_key(self, key, on):
        if key == "touch":
            self._apply_touch()
        elif key == "epp":
            if on:
                tweaks.set_epp(on)
            self.persist.update(EPP_IDX=tweaks.EPP_VALUES.index(on) if on else None)
        elif key == "wifiPowersaveOff":
            tweaks.set_wifi_powersave_off(on)
            self.persist.update(WIFI_PS_OFF=1 if on else None)
        elif key == "usbAutosuspendOff":
            tweaks.set_usb_autosuspend_off(on)
            self.persist.update(USB_AS_OFF=1 if on else None)
        elif key == "cpuBoostOff":
            tweaks.set_boost(not on)
            self.persist.update(BOOST_OFF=1 if on else None)
        elif key == "smtOff":
            tweaks.set_smt(not on)
            self.persist.update(SMT_OFF=1 if on else None)
        elif key == "audioPowersaveOff":
            tweaks.set_audio_ps(not on)
            self.persist.update(AUDIO_PS_OFF=1 if on else None)
        elif key == "ampsAwake":
            tweaks.set_amps_awake(on)
            self.persist.update(AMPS_AWAKE=1 if on else None)
        elif key == "splitLockMitigation":
            tweaks.set_splitlock(on)   # persisted by its sysctl.d drop-in

    def _apply_touch(self):
        mode = self.conf["system"].get("touch", "on")
        want = mode == "on" or (mode == "games" and not self.game)
        st = tweaks.touch_status()
        if st is not None and st["enabled"] != want:
            tweaks.set_touch(want)

    def apply_system(self):
        for k, on in self.conf["system"].items():
            if k == "touch":
                continue
            if on:
                try:
                    self.set_system(k, on)
                except Exception as e:
                    decky.logger.error(f"tweak {k} on load failed: {e}")

    def undo_system(self):
        """Only reverts what the user actually changed (non-default values)."""
        for k, v in list(self.conf["system"].items()):
            if v in (False, "", "on", None):
                continue
            try:
                self.set_system(k, "" if k == "epp" else ("on" if k == "touch" else False))
            except Exception as e:
                decky.logger.error(f"undo {k} failed: {e}")

    def tick(self, force=False):
        with self.lock:
            try:
                sysc = self.conf["system"]
                if sysc.get("wifiPowersaveOff"):
                    # Power Saver (tuned powersave-bazzite) turns it back on.
                    tweaks.wifi_enforce()
                # Power-profile switches (tuned / power-profiles-daemon) rewrite
                # these; put the user's choice back (writes only on a change).
                if sysc.get("cpuBoostOff") and tweaks.boost_status():
                    tweaks.set_boost(False)
                if sysc.get("ampsAwake"):
                    st = tweaks.amp_status()   # amps re-probe after resume
                    if st and not st["awake"]:
                        tweaks.set_amps_awake(True)
                if sysc.get("touch", "on") != "on":
                    self._apply_touch()
                if sysc.get("epp"):
                    st = tweaks.epp_status()
                    if st and st["current"] != sysc["epp"]:
                        tweaks.set_epp(sysc["epp"])
            except Exception as e:
                decky.logger.error(f"wifi enforce failed: {e}")
            try:
                snap = battery.snapshot()
                self._travel(snap)
                if not self.conf["rgb"]["managed"]:
                    return
                state = hhd.get_state() if hhd.available() else None
                self._apply_light(self._target(snap, state), state, force)
            except Exception as e:
                decky.logger.error(f"tick failed: {e}")

    def apply_static(self):
        """On unload: leave a non-changing light behind (no stale low-battery pulse)."""
        with self.lock:
            try:
                if self.conf["rgb"]["managed"]:
                    appid = (self.game or {}).get("appid")
                    g = self.conf["rgb"]["perGame"].get(appid) if appid else None
                    state = hhd.get_state() if hhd.available() else None
                    self._apply_light(self._scaled(g["light"] if g else self.conf["rgb"]["base"]), state, True)
            except Exception as e:
                decky.logger.error(f"apply_static failed: {e}")

    # ---------- charge ----------
    def apply_charge(self):
        with self.lock:
            c = self.conf["charge"]
            limit = 100 if c["travel"] else int(c["limit"])
            state = hhd.get_state() if hhd.available() else None
            be = battery.set_limit(limit, state)
            # Kernel path: asus-wmi forgets the limit on reboot, so the
            # restore unit re-applies it. HHD re-applies its own.
            try:
                self.persist.update(CHARGE_LIMIT=limit if be == "sysfs" and limit < 100 else None)
            except Exception as e:
                decky.logger.error(f"persist charge failed: {e}")
            return be

    def _travel(self, snap):
        ac = snap.get("ac")
        if self.conf["charge"]["travel"] and self.last_ac is not None and self.last_ac and not ac:
            decky.logger.info("Unplugged after full charge; restoring charge limit")
            self.conf["charge"]["travel"] = False
            self.save()
            self.apply_charge()
        self.last_ac = ac

    # ---------- games / buttons ----------
    def set_game(self, appid, name):
        with self.lock:
            self.game = {"appid": str(appid), "name": name} if appid else None
            try:
                self._apply_touch()
            except Exception as e:
                decky.logger.error(f"touch failed: {e}")
            try:
                self._apply_buttons()
            except Exception as e:
                decky.logger.error(f"buttons failed: {e}")
        self.tick()

    def _apply_buttons(self):
        """Per-game layout on launch; the user's own HHD setup comes back on exit.
        b["default"] holds what HHD had before we overrode it (persisted, so a
        Decky restart mid-game still restores it); None means nothing to undo."""
        if not hhd.available():
            return
        b = self.conf["buttons"]
        appid = (self.game or {}).get("appid")
        prof = b["perGame"].get(appid) if appid else None
        state = hhd.get_state()
        if prof:
            if b["default"] is None:
                cur = buttons.status(state)
                b["default"] = {"paddles": cur["paddles"], "nintendo": cur["nintendo"]}
                self.save()
            buttons.apply(prof.get("paddles"), prof.get("nintendo"), state)
        elif b["default"] is not None:
            buttons.apply(b["default"].get("paddles"), b["default"].get("nintendo"), state)
            b["default"] = None
            self.save()

    def reapply_buttons(self):
        with self.lock:
            self._apply_buttons()

    # ---------- loop ----------
    def _poll_screen(self) -> bool:
        """Debounced backlight read: a new level must hold for two reads
        (~1 s) before it's used, so dragging the slider doesn't spam HHD.
        Returns True when the effective level changed."""
        if not self.conf["rgb"].get("followScreen"):
            return False
        f = backlight.fraction()
        if f is None:
            return False
        f = round(f, 3)
        if f != self._screen_seen:
            self._screen_seen = f
            return False
        if f != self.screen:
            self.screen = f
            return True
        return False

    def run(self, stop: threading.Event, interval=5.0, fast=0.5):
        last = 0.0
        wall, mono = time.time(), time.monotonic()
        while not stop.is_set():
            now = time.monotonic()
            # Monotonic time stops during suspend, wall time doesn't: a gap
            # means we just woke up, so push everything again.
            woke = (time.time() - wall) - (now - mono) > 10
            wall, mono = time.time(), now
            if woke:
                decky.logger.info("Resume detected; re-applying lighting and tweaks")
                self.last_light = None
            changed = self._poll_screen()
            if woke or changed or now - last >= interval:
                last = now
                self.tick(force=woke)
            stop.wait(fast)
