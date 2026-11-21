"""Proton Picker - Decky backend.

Runs as the normal user (no "_root" flag): it only touches the user's own
Steam folder (compatibilitytools.d) and the network. All per-game Steam
changes (which compat tool a game uses) are made from the frontend through
Steam's own client API, SteamClient.Apps.SpecifyCompatTool.
"""

import asyncio
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from picker import settings, tools, releases, installer, protondb, steampaths  # noqa: E402


class Plugin:
    async def get_settings(self):
        return settings.load()

    async def save_settings(self, data: dict):
        settings.save(data)
        return True

    async def list_tools(self):
        return {"tools": tools.list_installed(), "compatDir": steampaths.user_compat_dir()}

    async def latest_release(self, family: str, force: bool = False):
        try:
            return {"ok": True, **(await asyncio.to_thread(releases.latest, family, force))}
        except Exception as e:
            decky.logger.warning(f"latest_release {family}: {e}")
            return {"ok": False, "error": str(e)}

    async def install(self, family: str):
        return installer.start(family)

    async def install_state(self):
        return installer.state()

    async def remove_tool(self, name: str):
        try:
            return await asyncio.to_thread(tools.remove, name)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def protondb_summaries(self, appids: list, force: bool = False):
        """Batch lookup; returns {appid: summary|None}. Errors map to 'error'.
        If ProtonDB can't be reached at all (offline, DNS, timeout), the rest of the batch is
        marked 'error' right away instead of waiting out a timeout per game."""
        out = {}
        offline = False
        ids = [str(a) for a in (appids or [])[:200]]
        for a in ids:
            if offline:
                out[a] = "error"
                continue
            try:
                out[a] = await asyncio.to_thread(protondb.summary, a, force, False)
            except urllib.error.HTTPError as e:
                decky.logger.warning(f"protondb {a}: HTTP {e.code}")
                out[a] = "error"
            except Exception as e:
                decky.logger.warning(f"protondb {a}: {e}; treating ProtonDB as unreachable for this batch")
                out[a] = "error"
                offline = True
        await asyncio.to_thread(protondb.flush)
        return out

    async def log(self, msg: str):
        decky.logger.info(f"[frontend] {msg}")

    async def _main(self):
        installer.cleanup_stale()
        decky.logger.info(f"Proton Picker loaded; compat dir {steampaths.user_compat_dir()}")

    async def _unload(self):
        decky.logger.info("Proton Picker unloaded")

    async def _uninstall(self):
        # Installed Proton builds stay: games may still be mapped to them.
        decky.logger.info("Proton Picker uninstalled; installed Proton builds left in place")
