"""Storage Sweep - Decky backend.

Runs as the normal user (no "root" flag): everything it cleans belongs to the user. Scans only
when the panel asks (button press), deletes only paths the scan returned and core.delete()
re-validates. No background work.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from sweep import core  # noqa: E402


class Plugin:
    async def scan(self, known_shortcuts: list, running: int):
        try:
            r = await asyncio.to_thread(core.scan, decky.DECKY_USER_HOME, known_shortcuts or [], int(running or 0))
            return {"ok": True, **r}
        except Exception as e:
            decky.logger.error(f"scan failed: {e!r}")
            return {"ok": False, "error": str(e)}

    async def delete(self, paths: list, running: int):
        try:
            r = await asyncio.to_thread(core.delete, list(paths or []), decky.DECKY_USER_HOME, int(running or 0))
            decky.logger.info(f"deleted {len(r['deleted'])} folders, freed {r['freed']} bytes, {len(r['failed'])} failed")
            return {"ok": True, **r}
        except Exception as e:
            decky.logger.error(f"delete failed: {e!r}")
            return {"ok": False, "error": str(e)}

    async def _main(self):
        pass

    async def _unload(self):
        pass
