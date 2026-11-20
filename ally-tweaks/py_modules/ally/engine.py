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

from . import battery, buttons, hhd, rgb, sensors, settings

DEFAULTS = {
    "rgb": {
        "managed": True,
        "base": {"mode": "solid", "hue": 200, "hue2": 300, "saturation": 100,
                 "brightness": 50, "speed": "medium", "direction": "left"},
        "reactive": "none",          # none | battery | temperature | tdp
        "lowBattery": True,
        "lowBatteryAt": 15,
        "offOnBattery": False,
        "perGame": {},               # appid -> {"name", "light"}
    },
    "charge": {"limit": 100, "travel": False},
    "buttons": {"perGame": {}, "default": None},  # appid -> {"name", "paddles", "nintendo"}
    "panel": {},                     # desired armoury toggles, only keys the user changed
}

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

    # ---------- settings ----------
    def save(self):
        settings.save(self.conf)

    def update(self, patch: dict):
        with self.lock:
            self.conf = _merge(self.conf, patch)
            self.save()
        self.tick(force=True)

    # ---------- lighting ----------
    def _target(self, snap: dict, state: dict | None):
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

    def tick(self, force=False):
        with self.lock:
            try:
                snap = battery.snapshot()
                self._travel(snap)
                if not self.conf["rgb"]["managed"] or not hhd.available():
                    return
                state = hhd.get_state()
                target = self._target(snap, state)
                key = rgb.to_state(target)
                if force or key != self.last_light:
                    rgb.apply(target, state)
                    self.last_light = key
            except Exception as e:
                decky.logger.error(f"tick failed: {e}")

    def apply_static(self):
        """On unload: leave a non-changing light behind (no stale low-battery pulse)."""
        with self.lock:
            try:
                if self.conf["rgb"]["managed"] and hhd.available():
                    appid = (self.game or {}).get("appid")
                    g = self.conf["rgb"]["perGame"].get(appid) if appid else None
                    rgb.apply(g["light"] if g else self.conf["rgb"]["base"])
            except Exception as e:
                decky.logger.error(f"apply_static failed: {e}")

    # ---------- charge ----------
    def apply_charge(self):
        with self.lock:
            c = self.conf["charge"]
            limit = 100 if c["travel"] else int(c["limit"])
            state = hhd.get_state() if hhd.available() else None
            return battery.set_limit(limit, state)

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
    def run(self, stop: threading.Event, interval=5.0):
        while not stop.is_set():
            self.tick()
            stop.wait(interval)
