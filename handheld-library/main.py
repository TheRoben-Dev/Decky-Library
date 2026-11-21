"""Handheld Library - Decky backend.

The frontend does all the Steam work (it reads the library and edits the collection through
Steam's own collectionStore). The backend only keeps settings and looks up ProtonDB tiers,
which the frontend can't fetch itself (CORS). Runs as the normal user.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from hhlib import pin, protondb, settings  # noqa: E402


def _settings_path() -> str:
    return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


class Plugin:
    _cache = None
    _pin = None

    def _pins(self):
        if self._pin is None:
            self._pin = pin.PinStore(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "pin.json"))
        return self._pin

    async def pin_status(self):
        return self._pins().status()

    async def pin_verify(self, code: str):
        return self._pins().verify(code)

    async def pin_set(self, new: str, current: str = ""):
        return self._pins().set(new, current)

    async def pin_clear(self, current: str):
        return self._pins().clear(current)

    def _pdb(self):
        if self._cache is None:
            self._cache = protondb.Cache(os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "protondb.json"))
        return self._cache

    async def get_settings(self):
        return settings.load(_settings_path())

    async def set_settings(self, d: dict):
        return settings.save(_settings_path(), d)

    async def protondb_tiers(self, appids: list):
        tiers = await protondb.lookup(self._pdb(), appids or [], decky.logger.warning)
        return {str(k): v for k, v in tiers.items()}

    async def _main(self):
        decky.logger.info("Handheld Library backend up")

    async def _unload(self):
        pass
