"""Nightgrid Movies - Decky backend.

Runs as the normal user (no "root" flag). Copies the bundled Nightgrid videos into Steam's
override folder (~/.steam/root/config/uioverrides/movies) as the startup movie and the suspend
animation; see py_modules/ngmovies/core.py for the file rules. The idle screensaver runs in the
frontend (src/screensaver.tsx); only its settings are kept here.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from ngmovies import core  # noqa: E402

MOVIES_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "movies")


def _override_dir() -> str:
    return os.path.join(decky.DECKY_USER_HOME, ".steam", "root", "config", "uioverrides", "movies")


def _store() -> core.Store:
    return core.Store(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"))


class Plugin:
    async def status(self):
        try:
            return {"ok": True, **await asyncio.to_thread(core.status, MOVIES_DIR, _override_dir(), _store())}
        except Exception as e:
            decky.logger.error(f"status failed: {e}")
            return {"ok": False, "error": str(e)}

    async def apply(self, kind: str, movie_id: str):
        try:
            st = await asyncio.to_thread(core.apply, kind, movie_id, MOVIES_DIR, _override_dir(), _store())
            decky.logger.info(f"{kind} -> {movie_id or 'Steam default'}")
            return {"ok": True, **st}
        except Exception as e:
            decky.logger.error(f"apply {kind}={movie_id} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def set_shuffle(self, on: bool):
        s = _store()
        s.data["shuffle"] = bool(on)
        s.save()
        return True

    async def movie_chunk(self, movie_id: str, offset: int):
        try:
            return {"ok": True, **await asyncio.to_thread(core.movie_chunk, MOVIES_DIR, movie_id, offset)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def get_saver(self):
        return _store().data["saver"]

    async def set_saver(self, saver: dict):
        s = _store()
        s.data["saver"] = core.clean_saver(saver or {})
        s.save()
        return s.data["saver"]

    async def _main(self):
        s = _store()
        if s.data["shuffle"] and s.data["boot"]:
            try:
                pick = await asyncio.to_thread(core.shuffle_boot, MOVIES_DIR, _override_dir(), s)
                decky.logger.info(f"shuffle: next startup movie {pick}")
            except Exception as e:
                decky.logger.error(f"shuffle failed: {e}")

    async def _unload(self):
        pass

    async def _uninstall(self):
        # Put Steam's own videos (or whatever was there before) back.
        try:
            await asyncio.to_thread(core.restore_all, MOVIES_DIR, _override_dir(), _store())
        except Exception as e:
            decky.logger.error(f"restore on uninstall failed: {e}")
