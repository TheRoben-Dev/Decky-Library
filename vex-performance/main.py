"""Vex Performance - Decky backend.

Runs as root (plugin flag "_root") so it can reach Handheld Daemon's root-only
UNIX socket, sysfs power/GPU knobs and the user's lsfg-vk config.

Everything Steam-side (FSR, frame cap, refresh, Steam TDP slider, render
resolution, launch options) is done from the frontend through Steam's own
client APIs. This backend handles what Steam can't: HHD, sysfs, lsfg-vk.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from vex import settings, hhd, power, lsfg, conflicts  # noqa: E402


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
            "hhd": hhd.status(),
            "power": power.capabilities(),
            "lsfg": lsfg.status(),
            "conflicts": conflicts.detect(),
        }

    # ---------- TDP / GPU ----------
    async def apply_power(self, backend: str, tdp_enabled: bool, tdp: int,
                          gpu_mode: str, gpu_min: int, gpu_max: int):
        """backend: 'hhd' | 'sysfs' | 'steam' | 'off'.
        For 'steam' the frontend sets TDP through Steam itself (HHD picks it up
        through its FUSE hook), so only the GPU part is handled here."""
        result = {"tdp": None, "gpu": None}
        try:
            use_hhd = backend in ("hhd", "steam") and hhd.available()
            if tdp_enabled and backend == "hhd":
                result["tdp"] = hhd.set_tdp(int(tdp)) if hhd.available() else "hhd-unavailable"
            elif tdp_enabled and backend == "sysfs":
                result["tdp"] = power.set_tdp_sysfs(int(tdp))
            if backend != "off":
                if use_hhd:
                    result["gpu"] = hhd.set_gpu(gpu_mode, int(gpu_min), int(gpu_max))
                else:
                    result["gpu"] = power.set_gpu_sysfs(gpu_mode, int(gpu_min), int(gpu_max))
        except Exception as e:  # never let a power write break the UI
            decky.logger.error(f"apply_power failed: {e}")
            result["error"] = str(e)
        return result

    async def reset_power(self, backend: str):
        """Back to automatic GPU clocks when no game is running."""
        try:
            if backend in ("hhd", "steam") and hhd.available():
                hhd.set_gpu("auto", 0, 0)
            elif backend != "off":
                power.set_gpu_sysfs("auto", 0, 0)
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

    async def log(self, msg: str):
        decky.logger.info(f"[frontend] {msg}")

    # ---------- lifecycle ----------
    async def _main(self):
        decky.logger.info("Vex Performance loaded")

    async def _unload(self):
        decky.logger.info("Vex Performance unloaded")

    async def _uninstall(self):
        # Leave lsfg-vk profiles we created? Remove them so nothing lingers.
        try:
            lsfg.remove_all_owned()
        except Exception as e:
            decky.logger.error(f"uninstall cleanup failed: {e}")
