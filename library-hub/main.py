"""Library Hub - Decky backend.

Installs, updates and removes everything published from TheRoben-Dev/Decky-Library: the
CSS Loader themes (Nightgrid, Lowpoly) and every Decky plugin in the repo, including Library Hub itself.

Runs as the normal user (no "root" flag):
- themes are written to ~/homebrew/themes/<Theme> here, after the checksum and zip checks;
- plugins are downloaded and checked here, then handed to Decky Loader's own installer by the
  frontend with the same URL and SHA-256. Decky asks for confirmation, checks the hash again,
  installs (as root) and reloads the plugin.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from libhub import plugins, releases, theme  # noqa: E402

LEGACY_UPDATER = "Nightgrid Updater"
INSTALL, REINSTALL, UPDATE, DOWNGRADE = 0, 1, 2, 3   # Decky's PluginInstallType


def _home() -> str:
    return decky.DECKY_USER_HOME


def _plugins_root() -> str:
    return os.path.dirname(os.path.realpath(decky.DECKY_PLUGIN_DIR))


def _cmp(installed, latest):
    a, b = releases.parse_version(installed or ""), releases.parse_version(latest or "")
    if a is None or b is None:
        return None
    return (a > b) - (a < b)


def _deps(rid: str, have: dict):
    out = []
    for d in plugins.DEPENDENCIES.get(rid, []):
        if d["kind"] == "decky":
            ok = d["name"] in have
        else:
            ok = plugins.steam_app_installed(_home(), d["appid"])
        out.append({**d, "installed": ok})
    return out


class Plugin:
    async def status(self, force: bool = False):
        """Every item with installed/latest versions and dependencies. Never raises.
        force=True skips the short release cache (the "Check for updates" button)."""
        have = plugins.installed(_plugins_root())
        out = {"items": [], "error": None, "cssLoader": plugins.CSS_LOADER in have,
               "legacyUpdater": LEGACY_UPDATER in have}
        try:
            cat = await asyncio.to_thread(releases.fetch_catalog, bool(force))
        except Exception as e:
            decky.logger.warning(f"release check failed: {e}")
            out["error"] = str(e)
            cat = {}
        for rid, it in sorted(cat.items(), key=lambda kv: (kv[0] != releases.SELF_ID,
                                                           kv[1]["kind"] != "theme", kv[1]["name"].lower())):
            if it["kind"] == "theme":
                inst = theme.installed_version(_home(), releases.THEMES[rid])
                inst = inst.lstrip("v") if inst else None
            else:
                inst = have.get(it["name"])
                if it["name"] in have and inst is None:
                    inst = "unknown"
            c = _cmp(inst, it["version"])
            out["items"].append({
                "id": rid, "kind": it["kind"], "name": it["name"],
                "installed": it["name"] in have if it["kind"] == "plugin" else inst is not None,
                "installedVersion": inst, "latest": it["version"],
                "updateAvailable": inst is not None and (c is None or c < 0),
                "isSelf": rid == releases.SELF_ID,
                "url": it["url"], "notes": it["notes"],
                "deps": await asyncio.to_thread(_deps, rid, have),
            })
        return out

    async def prepare_plugin(self, rid: str):
        """Downloads and checks a plugin release, then returns what Decky's installer needs."""
        try:
            cat = await asyncio.to_thread(releases.fetch_catalog)
            it = cat.get(rid)
            if not it or it["kind"] != "plugin":
                return {"ok": False, "error": f"No release found for {rid}."}
            data, sha = await asyncio.to_thread(releases.download, it)
            meta = plugins.inspect_zip(data)
            if meta["version"] and meta["version"] != it["version"]:
                return {"ok": False, "error": f"zip says {meta['version']} but the release is {it['version']}."}
            have = plugins.installed(_plugins_root())
            c = _cmp(have.get(meta["name"]), it["version"]) if meta["name"] in have else None
            kind = (INSTALL if meta["name"] not in have else
                    UPDATE if c is None or c < 0 else REINSTALL if c == 0 else DOWNGRADE)
            return {"ok": True, "artifact": releases.asset_url(it["zip"], it["tag"]), "hash": sha,
                    "name": meta["name"], "version": it["version"], "installType": kind}
        except Exception as e:
            decky.logger.error(f"prepare {rid} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def prepare_store_plugin(self, name: str):
        """CSS Loader (or another dependency) from Decky's own store, for Decky's installer."""
        if name != plugins.CSS_LOADER:
            return {"ok": False, "error": f"{name} isn't an allowed store dependency."}
        try:
            a = await asyncio.to_thread(plugins.fetch_store_artifact, name)
            if not a:
                return {"ok": False, "error": f"{name} isn't in Decky's store index."}
            return {"ok": True, **a, "installType": INSTALL}
        except Exception as e:
            decky.logger.error(f"store lookup for {name} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def install_theme(self, rid: str = releases.THEME_ID):
        folder = releases.THEMES.get(rid)
        if not folder:
            return {"ok": False, "error": f"{rid} isn't a theme from this repo."}
        try:
            cat = await asyncio.to_thread(releases.fetch_catalog)
            it = cat.get(rid)
            if not it:
                return {"ok": False, "error": f"No {folder} release published yet."}
            data, _ = await asyncio.to_thread(releases.download, it)
            ver = await asyncio.to_thread(theme.install_zip, data, _home(), decky.DECKY_PLUGIN_RUNTIME_DIR, folder)
            decky.logger.info(f"installed {folder} {ver} from {it['tag']}")
            return {"ok": True, "version": ver}
        except Exception as e:
            decky.logger.error(f"theme install failed: {e}")
            return {"ok": False, "error": str(e)}

    async def uninstall_theme(self, rid: str = releases.THEME_ID):
        folder = releases.THEMES.get(rid)
        if not folder:
            return {"ok": False, "error": f"{rid} isn't a theme from this repo."}
        try:
            removed = await asyncio.to_thread(theme.uninstall, _home(), decky.DECKY_PLUGIN_RUNTIME_DIR, folder)
            return {"ok": True, "removed": removed}
        except Exception as e:
            decky.logger.error(f"theme uninstall failed: {e}")
            return {"ok": False, "error": str(e)}

    async def _main(self):
        decky.logger.info("Library Hub loaded")

    async def _unload(self):
        pass
