"""Vex Performance - Decky backend.

Runs as root (plugin flag "root") so it can reach PowerStation on the system
bus, sysfs power/GPU knobs, the user's lsfg-vk config and (legacy, pre-Bazzite
44) Handheld Daemon's root-only socket.

Everything Steam-side (FSR, frame cap, refresh, Steam TDP slider, render
resolution, launch options) is done from the frontend through Steam's own
client APIs. This backend handles what Steam can't: PowerStation, sysfs, lsfg-vk, legacy HHD.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from vex import settings, hhd, power, powerstation, lsfg, conflicts  # noqa: E402


class Plugin:
    # ---------- settings ----------
    async def get_settings(self):
        return settings.load()

    async def save_settings(self, data: dict):
        settings.save(data)
        return True

    # ---------- environment / capability detection ----------
    async def get_environment(self):
        return {
            "powerstation": powerstation.status(),
            "hhd": hhd.status(),
            "power": power.capabilities(),
            "lsfg": lsfg.status(),
            "conflicts": conflicts.detect(),
        }

    # ---------- TDP / GPU ----------
    def _gpu_route(self, backend: str):
        """GPU clocks: PowerStation if it's running (Bazzite 44+), legacy HHD only
        when chosen explicitly, otherwise amdgpu sysfs."""
        if backend == "off":
            return None
        if powerstation.available():
            return "powerstation"
        if backend == "hhd" and hhd.available():
            return "hhd"
        return "sysfs"

    def _set_gpu(self, route, mode, gmin, gmax):
        if route == "powerstation":
            return powerstation.set_gpu(mode, gmin, gmax)
        if route == "hhd":
            return hhd.set_gpu(mode, gmin, gmax)
        if route == "sysfs":
            return power.set_gpu_sysfs(mode, gmin, gmax)
        return None

    async def apply_power(self, backend: str, tdp_enabled: bool, tdp: int,
                          gpu_mode: str, gpu_min: int, gpu_max: int):
        """backend: 'steam' | 'powerstation' | 'sysfs' | 'hhd' (legacy) | 'off'.
        For 'steam' the frontend sets TDP through Steam's own slider, so only
        the GPU part is handled here."""
        result = {"tdp": None, "gpu": None}
        try:
            if tdp_enabled:
                if backend == "powerstation":
                    result["tdp"] = powerstation.set_tdp(int(tdp))
                elif backend == "hhd":
                    result["tdp"] = hhd.set_tdp(int(tdp)) if hhd.available() else "hhd-unavailable"
                elif backend == "sysfs":
                    result["tdp"] = power.set_tdp_sysfs(int(tdp))
            # "skip": the profile leaves GPU clocks alone, so Steam's own GPU clock slider
            # (or whatever the user set) isn't overwritten with "auto" on every launch.
            if gpu_mode != "skip":
                route = self._gpu_route(backend)
                result["gpuPath"] = route
                result["gpu"] = self._set_gpu(route, gpu_mode, int(gpu_min), int(gpu_max))
        except Exception as e:  # never let a power write break the UI
            decky.logger.error(f"apply_power failed: {e}")
            result["error"] = str(e)
        return result

    async def reset_power(self, backend: str):
        """Back to automatic GPU clocks when no game is running."""
        try:
            self._set_gpu(self._gpu_route(backend), "auto", 0, 0)
        except Exception as e:
            decky.logger.error(f"reset_power failed: {e}")
        return True

    # ---------- lsfg-vk ----------
    async def lsfg_set_game(self, appid: str, name: str, enabled: bool,
                            multiplier: int, flow_scale: float, performance_mode: bool):
        try:
            return lsfg.set_game(str(appid), name, bool(enabled), int(multiplier),
                                 float(flow_scale), bool(performance_mode))
        except Exception as e:
            decky.logger.error(f"lsfg_set_game failed: {e}")
            return {"ok": False, "error": str(e)}

    async def lsfg_install(self, force: bool = False):
        try:
            return lsfg.install_layer(bool(force))
        except Exception as e:
            decky.logger.error(f"lsfg_install failed: {e}")
            return {"ok": False, "error": str(e)}

    async def log(self, msg: str):
        decky.logger.info(f"[frontend] {msg}")

    # ---------- lifecycle ----------
    async def _main(self):
        decky.logger.info("Vex Performance loaded")

    async def _unload(self):
        decky.logger.info("Vex Performance unloaded")

    async def _uninstall(self):
        # Remove the lsfg-vk profiles and layer files we installed so nothing lingers.
        try:
            lsfg.remove_all_owned()
            lsfg.uninstall_layer()
        except Exception as e:
            decky.logger.error(f"uninstall cleanup failed: {e}")
