"""Ally Tweaks - Decky backend.

Runs as root (plugin flag "_root") to reach Handheld Daemon's root-only socket
and the documented asus-wmi / asus-armoury / power_supply sysfs files.

Safety rules this plugin follows:
  * Lighting, back buttons and charge limit go through Handheld Daemon's own
    settings API, so HHD stays in charge of talking to the MCU.
  * Direct writes only to documented kernel attributes: power_supply
    charge_control_end_threshold, asus-armoury panel_overdrive / boot_sound.
  * Nothing touches TDP, clocks, voltages, fans or thermal policy, and no raw
    MCU/EC commands or firmware updates are ever sent.
"""
import asyncio
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from ally import armoury, battery, buttons, device, hhd, rgb  # noqa: E402
from ally.engine import Engine  # noqa: E402


class Plugin:
    engine: Engine = None
    stop: threading.Event = None
    thread: threading.Thread = None

    # ---------- state for the UI ----------
    async def get_state(self):
        return await asyncio.to_thread(self._state)

    def _state(self):
        e = self.engine
        out = {
            "device": device.info(),
            "hhd": {"running": hhd.available()},
            "battery": battery.snapshot(),
            "panel": armoury.read_all(),
            "settings": e.conf,
            "lightReason": e.reason,
            "game": e.game,
        }
        st = None
        if hhd.available():
            try:
                st = hhd.get_state()
                out["rgb"] = rgb.status(st)
                out["buttons"] = buttons.status(st)
            except Exception as ex:
                out["hhd"]["error"] = str(ex)
        out["chargeBackend"] = battery.backend(st)
        return out

    async def save_settings(self, patch: dict):
        await asyncio.to_thread(self.engine.update, patch)
        return True

    # ---------- actions ----------
    async def set_game(self, appid: str, name: str):
        await asyncio.to_thread(self.engine.set_game, appid, name)
        return True

    async def set_charge(self, limit: int, travel: bool):
        def run():
            self.engine.conf["charge"].update({"limit": int(limit), "travel": bool(travel)})
            self.engine.save()
            return self.engine.apply_charge()
        try:
            return {"ok": True, "backend": await asyncio.to_thread(run)}
        except Exception as e:
            decky.logger.error(f"set_charge failed: {e}")
            return {"ok": False, "error": str(e)}

    async def set_rgb_flags(self, boot: bool, charging: bool):
        try:
            await asyncio.to_thread(rgb.set_flags, boot, charging)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def set_panel(self, key: str, on: bool):
        def run():
            ok = armoury.write(key, on)
            if ok:
                self.engine.conf["panel"][key] = bool(on)
                self.engine.save()
            return ok
        try:
            return {"ok": await asyncio.to_thread(run)}
        except Exception as e:
            decky.logger.error(f"set_panel failed: {e}")
            return {"ok": False, "error": str(e)}

    async def set_buttons_global(self, paddles: str, nintendo: bool):
        """Changes HHD's own (all-games) setup. Only offered by the UI when no
        per-game override is active."""
        try:
            await asyncio.to_thread(buttons.apply, paddles, nintendo)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def reapply_buttons(self):
        try:
            await asyncio.to_thread(self.engine.reapply_buttons)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def log(self, msg: str):
        decky.logger.info(f"[frontend] {msg}")

    # ---------- lifecycle ----------
    async def _main(self):
        self.engine = Engine()
        info = device.info()
        decky.logger.info(f"Ally Tweaks loaded on '{info['product']}' ({info['cpu']})")

        def startup():
            e = self.engine
            # Re-apply what the hardware may have forgotten across a reboot.
            try:
                e.apply_charge()
            except Exception as ex:
                decky.logger.error(f"charge limit on load failed: {ex}")
            for key, on in e.conf.get("panel", {}).items():
                try:
                    armoury.write(key, on)
                except Exception as ex:
                    decky.logger.error(f"panel {key} on load failed: {ex}")
            # If Decky restarted mid-game, undo any per-game button override.
            try:
                e.reapply_buttons()
            except Exception as ex:
                decky.logger.error(f"buttons on load failed: {ex}")
            e.tick(force=True)

        await asyncio.to_thread(startup)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.engine.run, args=(self.stop,), daemon=True)
        self.thread.start()

    async def _unload(self):
        if self.stop:
            self.stop.set()
        if self.engine:
            await asyncio.to_thread(self.engine.apply_static)
        decky.logger.info("Ally Tweaks unloaded")

    async def _uninstall(self):
        # Leave the hardware as stock-like as possible: no charge cap and the
        # user's own button layout back. Lighting is left as last set in HHD.
        try:
            e = self.engine or Engine()
            e.conf["charge"].update({"limit": 100, "travel": False})
            e.apply_charge()
            e.game = None
            e.reapply_buttons()
        except Exception as ex:
            decky.logger.error(f"uninstall cleanup failed: {ex}")
