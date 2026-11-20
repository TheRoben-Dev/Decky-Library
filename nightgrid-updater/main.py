"""Nightgrid Updater - Decky backend.

Runs as the normal user (no "root" flag): it only reads GitHub releases and writes
~/homebrew/themes/Nightgrid. Reloading CSS Loader happens in the frontend.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from ngupdate import updater  # noqa: E402


def _home() -> str:
    return decky.DECKY_USER_HOME


class Plugin:
    async def status(self):
        """Installed vs latest release. Never raises: errors come back as text."""
        out = {"installed": updater.installed_version(_home()), "latest": None,
               "updateAvailable": False, "error": None, "release": None}
        try:
            rel = await asyncio.to_thread(updater.latest)
        except Exception as e:
            decky.logger.warning(f"release check failed: {e}")
            out["error"] = str(e)
            return out
        if not rel:
            out["error"] = "No Nightgrid release published yet."
            return out
        out["latest"] = rel["version"]
        out["release"] = {"tag": rel["tag"], "url": rel["url"], "notes": rel["notes"]}
        cur = updater.parse_version(out["installed"] or "")
        out["updateAvailable"] = cur is None or updater.parse_version(rel["version"]) > cur
        return out

    async def install_latest(self):
        try:
            rel = await asyncio.to_thread(updater.latest)
            if not rel:
                return {"ok": False, "error": "No Nightgrid release published yet."}
            data = await asyncio.to_thread(updater.download, rel)
            ver = await asyncio.to_thread(
                updater.install_zip, data, _home(), decky.DECKY_PLUGIN_RUNTIME_DIR)
            decky.logger.info(f"installed Nightgrid {ver} from {rel['tag']}")
            return {"ok": True, "version": ver}
        except Exception as e:
            decky.logger.error(f"install failed: {e}")
            return {"ok": False, "error": str(e)}

    async def _main(self):
        decky.logger.info("Nightgrid Updater loaded")

    async def _unload(self):
        pass
