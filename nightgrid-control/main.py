"""Nightgrid Control - Decky backend.

Runs as the normal user (no "root" flag). Does nothing in the background: hosts are only
contacted when the panel asks (it refreshes while it is open), plus the action buttons.
"""
import asyncio
import os
import pwd
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from ngc import agefile, profile, remote  # noqa: E402

PARALLEL = 6
TRANSIENT = ("rebooting", "stopping", "waking")


def _err(e: Exception) -> dict:
    return {"ok": False, "error": str(e) or e.__class__.__name__}


class Plugin:
    def __init__(self):
        self.home = decky.DECKY_USER_HOME
        self.store = profile.Store(decky.DECKY_PLUGIN_SETTINGS_DIR)
        self.ctx = remote.Ctx(self.home, decky.DECKY_PLUGIN_SETTINGS_DIR, profile.app_data_dir(self.home))
        self.cache = {}  # host id -> last status
        self.refreshing = None
        self.local_cache = (None, None)  # (mtime, parsed)

    # ------------------------------------------------------------ profile

    def _profile(self):
        """(meta, hosts, secrets). An imported export wins; else Nightgrid on this device."""
        p = self.store.load()
        if p:
            return ({"source": "file", "file": p.get("file"), "importedAt": p.get("importedAt"),
                     "createdAt": p.get("createdAt"), "appVersion": p.get("appVersion"),
                     "passwords": len(p.get("secrets") or {})},
                    p["hosts"], p.get("secrets") or {})
        db = profile.local_db(self.home)
        if db:
            try:
                mt = os.path.getmtime(db)
                if self.local_cache[0] != mt:
                    self.local_cache = (mt, profile.read_local(self.home))
                d = self.local_cache[1]
                return {"source": "local", "file": db, "passwords": 0}, d["hosts"], {}
            except Exception as e:
                decky.logger.error(f"reading Nightgrid's database failed: {e!r}")
                return {"source": "local", "file": db, "error": str(e), "passwords": 0}, [], {}
        return {"source": None}, [], {}

    def _host(self, host_id):
        meta, hosts, secrets = self._profile()
        h = next((x for x in hosts if x["id"] == int(host_id)), None)
        if not h:
            raise ValueError("host isn't in the profile any more")
        return h, hosts, secrets

    async def get_state(self):
        try:
            meta, hosts, secrets = self._profile()
            prefs = self.store.prefs()
            pub = [{k: v for k, v in h.items() if k not in ("identity",)} | {"hasPassword": str(h["id"]) in secrets}
                   for h in hosts]
            return {"ok": True, "profile": meta, "hosts": pub, "status": list(self.cache.values()), "prefs": prefs,
                    "localAvailable": bool(profile.local_db(self.home))}
        except Exception as e:
            decky.logger.error(f"get_state failed: {e!r}")
            return _err(e)

    async def find_profiles(self):
        try:
            user = pwd.getpwuid(os.getuid()).pw_name
            return {"ok": True, "files": await asyncio.to_thread(profile.find_exports, self.home, user)}
        except Exception as e:
            return _err(e)

    async def import_profile(self, path: str, passphrase: str):
        try:
            path = os.path.realpath(str(path))
            if not path.endswith(".age") or not os.path.isfile(path):
                return {"ok": False, "error": "file not found"}
            with open(path, "rb") as f:
                data = f.read(agefile.MAX_BYTES + 1)
            parsed = await asyncio.to_thread(profile.read_export, data, str(passphrase or ""))
            self.store.save_export(path, parsed)
            self.cache.clear()
            decky.logger.info(f"imported profile {path}: {len(parsed['hosts'])} hosts, "
                              f"{len(parsed['secrets'])} with saved passwords")
            return {"ok": True, "hosts": len(parsed["hosts"]), "passwords": len(parsed["secrets"])}
        except agefile.WrongPassphrase:
            return {"ok": False, "error": "Wrong passphrase", "wrong": True}
        except Exception as e:
            decky.logger.error(f"import failed: {e!r}")
            return _err(e)

    async def forget_profile(self):
        self.store.forget()
        self.cache.clear()
        return {"ok": True}

    async def set_prefs(self, patch: dict):
        try:
            return {"ok": True, "prefs": self.store.set_prefs(dict(patch or {}))}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ status

    async def _refresh(self, ids):
        meta, hosts, secrets = self._profile()
        sem = asyncio.Semaphore(PARALLEL)
        targets = [h for h in hosts if (ids is None or h["id"] in ids) and h["hostname"]]

        async def one(h):
            async with sem:
                try:
                    r = await remote.status(self.ctx, h, hosts, secrets.get(str(h["id"]), {}))
                except Exception as e:
                    decky.logger.error(f"status {h['name']} failed: {e!r}")
                    r = {"id": h["id"], "state": "error", "error": str(e), "at": time.time()}
                prev = self.cache.get(h["id"]) or {}
                # Keep "rebooting / shutting down / waking" on screen while the host is
                # (expectedly) not answering, for up to 3 minutes after the button press.
                if (r["state"] in ("offline", "sleep", "away") and prev.get("state") in TRANSIENT
                        and time.time() - prev.get("since", 0) < 180):
                    r = {**r, "state": prev["state"], "since": prev["since"]}
                elif (r["state"] == "ok" and prev.get("state") in ("rebooting", "stopping")
                        and time.time() - prev.get("since", 0) < 20):
                    r = {"id": h["id"], "state": prev["state"], "since": prev["since"], "at": r["at"]}
                self.cache[h["id"]] = r

        await asyncio.gather(*(one(h) for h in targets))
        live = {h["id"] for h in hosts}
        for k in list(self.cache):
            if k not in live:
                del self.cache[k]

    async def refresh(self, ids=None):
        """Checks hosts now (one run at a time; a second call waits for the running one)."""
        try:
            want = None if ids is None else {int(i) for i in ids}
            if self.refreshing and not self.refreshing.done():
                await self.refreshing
                if want is None:
                    return {"ok": True, "status": list(self.cache.values())}
            self.refreshing = asyncio.ensure_future(self._refresh(want))
            await self.refreshing
            return {"ok": True, "status": list(self.cache.values())}
        except Exception as e:
            decky.logger.error(f"refresh failed: {e!r}")
            return _err(e)

    # ------------------------------------------------------------ actions

    async def power(self, host_id: int, action: str):
        try:
            h, hosts, secrets = self._host(host_id)
            r = await remote.power(self.ctx, h, hosts, secrets.get(str(h["id"]), {}), str(action))
            decky.logger.info(f"{action} {h['name']}: {r}")
            if r.get("ok"):
                self.cache[h["id"]] = {**self.cache.get(h["id"], {"id": h["id"]}),
                                       "state": "rebooting" if action == "reboot" else "stopping",
                                       "since": time.time(), "at": time.time()}
            return r
        except Exception as e:
            decky.logger.error(f"power failed: {e!r}")
            return _err(e)

    async def wake(self, host_id: int):
        try:
            h, hosts, secrets = self._host(host_id)
            r = await remote.wake(self.ctx, h, hosts, secrets)
            decky.logger.info(f"wake {h['name']}: {r}")
            if r.get("ok"):
                self.cache[h["id"]] = {"id": h["id"], "state": "waking", "since": time.time(), "at": time.time()}
            return r
        except Exception as e:
            return _err(e)

    async def device_key(self, create: bool = False):
        try:
            r = await remote.device_key(self.ctx, bool(create))
            if create and r.get("ok") and r.get("pub"):
                r["exported"] = self._export_pub(r["pub"])
            return r
        except Exception as e:
            return _err(e)

    def _export_pub(self, pub: str):
        """Drops the public key next to the imported profile (often a synced folder), so it is
        at hand in Nightgrid on the computer: Settings > Connections > SSH keys."""
        p = self.store.load()
        folder = os.path.dirname(p["file"]) if p and p.get("file") else os.path.join(self.home, "Downloads")
        try:
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, f"nightgrid-control-{os.uname().nodename}.pub")
            with open(dst, "w") as f:
                f.write(pub + "\n")
            return dst
        except OSError:
            return None

    async def install_key(self):
        """Adds this device's key on every host whose password the profile carries."""
        try:
            k = await remote.device_key(self.ctx, False)
            if not k.get("exists"):
                return {"ok": False, "error": "create the key first"}
            meta, hosts, secrets = self._profile()
            done, failed = [], []
            for h in hosts:
                s = secrets.get(str(h["id"]), {})
                if not s.get("host-password") or not h["hostname"]:
                    continue
                r = await remote.install_key(self.ctx, h, hosts, s, k["pub"])
                (done if r.get("ok") else failed).append({"name": h["name"], "error": r.get("error")})
            return {"ok": True, "done": done, "failed": failed}
        except Exception as e:
            return _err(e)

    async def _main(self):
        pass

    async def _unload(self):
        t = self.refreshing
        if t and not t.done():
            t.cancel()
