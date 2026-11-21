"""Epic Library - Decky backend.

Runs as the normal user (no "root" flag) and does nothing in the background:
- Legendary (bundled, run as its own process) signs in to Epic, lists owned games, downloads and
  updates them; its sign-in data stays in this plugin's settings folder;
- the Epic store's public catalog is read only while the Browse tab is open;
- downloads run one at a time, only when asked, and report progress as events;
- Steam shortcuts and artwork are made by the frontend through SteamClient. Each shortcut starts
  the game through runtime/launch.sh, which fetches a fresh Epic launch token right before Steam's
  own Proton command runs.
Updates are checked only when the library page asks for it (on open, at most every few hours, or
the Check button).
"""
import asyncio
import base64
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from epiclib import catalog, library  # noqa: E402
from epiclib.device import DeviceLogin  # noqa: E402
from epiclib.handoff import Handoff  # noqa: E402
from epiclib.legendary import Cancelled, Legendary, LegendaryError, find_python  # noqa: E402
from epiclib.store import Meta, Settings, read_json, write_json  # noqa: E402

PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
CODE_RE = re.compile(r"\b[0-9a-f]{32}\b")
LIBRARY_TTL = 30 * 60
LIBRARY_FORMAT = 2               # bump when library.build() changes what it keeps
UPDATE_TTL = 6 * 3600
FREE_TTL = 30 * 60
MAX_IMAGE = 8 * 1024 * 1024
IMAGE_HOSTS = (".epicgames.com", ".unrealengine.com", ".akamaized.net", ".epicgames.net")


def _err(e: BaseException) -> dict:
    if not isinstance(e, (LegendaryError, catalog.CatalogError)):
        decky.logger.error(f"unexpected error: {e!r}")
    return {"ok": False, "error": str(e) or e.__class__.__name__, "status": getattr(e, "status", 0)}


def steam_root(home: str) -> str:
    for p in (".local/share/Steam", ".steam/steam", ".steam/root"):
        full = os.path.join(home, p)
        if os.path.isdir(os.path.join(full, "steamapps")):
            return os.path.realpath(full)
    return os.path.join(home, ".local/share/Steam")


def free_bytes(path: str) -> int:
    p = path
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    try:
        return shutil.disk_usage(p or "/").free
    except OSError:
        return 0


def extract_code(text: str) -> str:
    """The authorization code from whatever was pasted: the bare code, or Epic's whole JSON."""
    m = re.search(r'"authorizationCode"\s*:\s*"([0-9a-fA-F]{32})"', text or "")
    if m:
        return m.group(1).lower()
    m = CODE_RE.search((text or "").lower())
    return m.group(0) if m else ""


class Plugin:
    def __init__(self):
        self.home = decky.DECKY_USER_HOME
        self.settings = Settings(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"))
        self.meta = Meta(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "games.json"))
        self.data = decky.DECKY_PLUGIN_RUNTIME_DIR
        self.runtime = os.path.join(self.data, "runtime")
        self.lgd = Legendary(self.runtime, os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "legendary"),
                             os.path.join(self.data, "cache"))
        self.loop = None
        self.jobs: list = []          # queue, first = running
        self.job_lock = threading.Lock()
        self.worker = None
        self.handoff = Handoff(self._handoff_code)
        self.device = DeviceLogin(self._device_code)
        self.versions: dict = {}      # app -> latest build version (from Legendary's asset list)
        self.last_update_check = 0.0
        self.free_cache: dict = {}

    # ------------------------------------------------------------ plumbing

    def _emit(self, event: str, payload) -> None:
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(decky.emit(event, payload), self.loop)
            except RuntimeError:
                pass

    def _root(self) -> str:
        return self.settings.data["root"] or os.path.join(self.home, "Games", "epic")

    def _public(self) -> dict:
        u = self.lgd.user()
        return {**self.settings.data, "root": self._root(), "home": self.home, "signedIn": bool(u),
                "user": u, "problem": self.lgd.ready()}

    def _library_path(self) -> str:
        return os.path.join(self.data, "library.json")

    def _drop_library_cache(self) -> None:
        try:
            os.unlink(self._library_path())
        except OSError:
            pass

    def _installed(self) -> dict:
        if not self.versions:
            self.versions = self.lgd.latest_versions()
        return library.installed_view(self.lgd.installed(), self.meta.games, self.versions, os.path.isdir)

    def _job_view(self, j: dict) -> dict:
        return {k: j[k] for k in ("app", "title", "action", "phase", "done", "total", "speed", "error") if k in j}

    def launch_options(self, app: str) -> str:
        return f'"{os.path.join(self.runtime, "launch.sh")}" {app} %command%'

    # ------------------------------------------------------------ runtime

    def _install_runtime(self) -> None:
        """Copies the bundled Legendary + launch wrapper to the plugin's data folder (once per
        version), so Steam shortcuts point at a path that survives plugin updates."""
        src = os.path.join(PLUGIN_DIR, "runtime")
        stamp_src = os.path.join(PLUGIN_DIR, "package.json")
        try:
            want = str(os.path.getmtime(stamp_src)) + ":" + str(os.path.getsize(stamp_src))
        except OSError:
            want = "dev"
        stamp = os.path.join(self.runtime, ".stamp")
        try:
            with open(stamp, encoding="utf-8") as f:
                have = f.read().strip()
        except OSError:
            have = ""
        if have != want and os.path.isdir(src):
            tmp = self.runtime + ".new"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("__pycache__"))
            os.chmod(os.path.join(tmp, "launch.sh"), 0o755)
            with open(os.path.join(tmp, ".stamp"), "w", encoding="utf-8") as f:
                f.write(want)
            old = self.runtime + ".old"
            shutil.rmtree(old, ignore_errors=True)
            if os.path.isdir(self.runtime):
                os.replace(self.runtime, old)
            os.replace(tmp, self.runtime)
            shutil.rmtree(old, ignore_errors=True)
        os.makedirs(self.lgd.config, exist_ok=True)
        os.chmod(self.lgd.config, 0o700)    # holds the Epic sign-in token
        py = find_python() or "/usr/bin/python3"
        self.lgd.python = py if os.access(py, os.X_OK) else ""
        env = (f'EPIC_PYTHON="{py}"\nEPIC_CONFIG="{self.lgd.config}"\nEPIC_CACHE="{self.lgd.cache}"\n'
               f'EPIC_LOGS="{os.path.join(self.data, "logs")}"\n')
        p = os.path.join(self.runtime, "paths.env")
        if read_text(p) != env and os.path.isdir(self.runtime):
            with open(p, "w", encoding="utf-8") as f:
                f.write(env)

    # ------------------------------------------------------------ settings / sign-in

    async def settings_get(self):
        return self._public()

    def _sign_in(self, text: str) -> tuple:
        code = extract_code(text)
        if not code:
            return False, "That isn't an Epic authorization code. Copy the text Epic shows after you sign in."
        try:
            u = self.lgd.auth(code)
        except LegendaryError as e:
            return False, str(e)
        self._drop_library_cache()
        self.versions = {}
        decky.logger.info("signed in to Epic")
        return True, f"Signed in as {u.get('name') or 'your Epic account'}."

    def _handoff_code(self, text: str) -> tuple:
        ok, msg = self._sign_in(text)
        if ok:
            self._emit("epic_signed_in", self._public())
        return ok, msg

    async def sign_in(self, text: str):
        ok, msg = await asyncio.to_thread(self._sign_in, text)
        return {"ok": ok, "message": msg, "settings": self._public()}

    async def sign_out(self):
        await asyncio.to_thread(self.lgd.sign_out)
        self._drop_library_cache()
        self.versions = {}
        return self._public()

    async def handoff_start(self):
        return await asyncio.to_thread(self.handoff.start)

    async def handoff_status(self):
        return {**self.handoff.status(), "signedIn": bool(self.lgd.user())}

    async def handoff_stop(self):
        await asyncio.to_thread(self.handoff.stop)
        return True

    def _device_code(self, exchange: str) -> tuple:
        try:
            u = self.lgd.auth_token(exchange)
        except LegendaryError as e:
            return False, str(e)
        self._drop_library_cache()
        self.versions = {}
        decky.logger.info("signed in to Epic (device code)")
        self._emit("epic_signed_in", self._public())
        return True, f"Signed in as {u.get('name') or 'your Epic account'}."

    async def device_start(self):
        return await asyncio.to_thread(self.device.start)

    async def device_status(self):
        return self.device.status()

    async def device_stop(self):
        self.device.stop()
        return True

    async def set_options(self, opts: dict):
        s = self.settings.data
        if isinstance(opts.get("tool"), str):
            s["tool"] = opts["tool"][:120]
        for k in ("dlcs", "show_all"):
            if k in opts:
                s[k] = bool(opts[k])
        if isinstance(opts.get("root"), str):
            want = os.path.realpath(opts["root"]) if opts["root"] else ""
            match = next((r["path"] for r in self._roots() if os.path.realpath(r["path"]) == want), None)
            if want and not match:
                return {"ok": False, "error": "That folder isn't one of the offered locations"}
            internal = os.path.realpath(os.path.join(self.home, "Games", "epic"))
            s["root"] = "" if not want or want == internal else match
        self.settings.save()
        return {"ok": True, "settings": self._public()}

    def _roots(self) -> list:
        """Internal storage plus every writable removable drive (SD card, USB)."""
        out = [{"path": os.path.join(self.home, "Games", "epic"), "label": "Internal"}]
        seen = set()
        for base in (f"/run/media/{os.path.basename(self.home)}", "/run/media"):
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for n in names:
                m = os.path.join(base, n)
                if m in seen or not os.path.ismount(m) or not os.access(m, os.W_OK):
                    continue
                seen.add(m)
                out.append({"path": os.path.join(m, "Games", "epic"), "label": f"Drive · {n}"})
        cur = self._root()
        if not any(os.path.realpath(r["path"]) == os.path.realpath(cur) for r in out):
            out.append({"path": cur, "label": "Current (not mounted)" if not os.path.isdir(os.path.dirname(cur)) else "Current"})
        for r in out:
            r["free"] = free_bytes(r["path"])
        return out

    async def roots(self):
        return await asyncio.to_thread(self._roots)

    # ------------------------------------------------------------ library

    def _library(self, refresh: bool) -> dict:
        u = self.lgd.user()
        if not u:
            raise LegendaryError("Not signed in", 401)
        cache = read_json(self._library_path(), {})
        fresh = cache.get("v") == LIBRARY_FORMAT and cache.get("user") == u["id"] and time.time() - float(cache.get("at", 0)) < LIBRARY_TTL
        if refresh or not fresh or not isinstance(cache.get("games"), list):
            raw = self.lgd.owned()
            self.versions = self.lgd.latest_versions()
            cache = {"v": LIBRARY_FORMAT, "at": time.time(), "user": u["id"], "games": library.build(raw, self.versions)}
            write_json(self._library_path(), cache)
        games = cache["games"]
        if not self.settings.data["show_all"]:
            games = [g for g in games if not g.get("third_party")]
        return {"games": games, "at": cache["at"]}

    async def library(self, refresh: bool = False):
        try:
            lib = await asyncio.to_thread(self._library, bool(refresh))
            inst = await asyncio.to_thread(self._installed)
        except Exception as e:
            return _err(e)
        due = time.time() - self.last_update_check > UPDATE_TTL and bool(inst)
        return {"ok": True, **lib, "installed": inst, "jobs": [self._job_view(j) for j in self.jobs],
                "updatesDue": due}

    def _game(self, app: str) -> dict | None:
        for g in read_json(self._library_path(), {}).get("games") or []:
            if g.get("app") == app:
                return g
        return None

    async def game(self, app: str):
        app = str(app)
        g = self._game(app)
        inst = (await asyncio.to_thread(self._installed)).get(app)
        if not g and inst:
            g = {"app": app, "title": inst["title"], "ns": "", "tall": "", "wide": "", "logo": "", "developer": "",
                 "description": "", "version": inst["latest"], "installable": True, "third_party": "", "dlcs": 0,
                 "cloud_saves": False}
        if not g:
            return {"ok": False, "error": "This game isn't in your Epic library (refresh the library)."}
        m = self.meta.get(app)
        return {"ok": True, "game": g, "installed": inst, "resume": bool(self.lgd.resume_file(app)) and not inst,
                "partial": m.get("partial", "")}

    async def install_info(self, app: str):
        try:
            return {"ok": True, **await asyncio.to_thread(self.lgd.info, str(app))}
        except Exception as e:
            return _err(e)

    async def installed_list(self):
        return await asyncio.to_thread(self._installed)

    # ------------------------------------------------------------ store

    async def browse(self, opts: dict):
        o = opts if isinstance(opts, dict) else {}
        try:
            return {"ok": True, **await asyncio.to_thread(catalog.search, o, os.path.join(self.data, "cache"))}
        except Exception as e:
            return _err(e)

    async def free_now(self, country: str = "US"):
        c = self.free_cache
        key = str(country or "US")
        if c.get("key") == key and time.time() - c.get("at", 0) < FREE_TTL:
            return {"ok": True, "items": c["items"]}
        try:
            items = await asyncio.to_thread(catalog.free_now, key)
        except Exception as e:
            return _err(e)
        self.free_cache = {"key": key, "at": time.time(), "items": items}
        return {"ok": True, "items": items}

    async def image(self, url: str):
        """An Epic CDN image as base64, for drawing Steam artwork on a canvas without tainting it."""
        u = urllib.parse.urlparse(url or "")
        host = (u.hostname or "").lower()
        if u.scheme != "https" or not any(host.endswith(h) or host == h.lstrip(".") for h in IMAGE_HOSTS):
            return {"ok": False, "error": "Not an Epic image"}

        def fetch():
            req = urllib.request.Request(url, headers={"User-Agent": catalog.UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                data = r.read(MAX_IMAGE + 1)
            if len(data) > MAX_IMAGE:
                raise ValueError("Image too large")
            ext = "png" if "png" in ctype or data[:8] == b"\x89PNG\r\n\x1a\n" else \
                  "webp" if "webp" in ctype or data[8:12] == b"WEBP" else "jpeg"
            return data, ext
        try:
            data, ext = await asyncio.to_thread(fetch)
            return {"ok": True, "data": base64.b64encode(data).decode("ascii"), "ext": ext}
        except Exception as e:
            return {"ok": False, "error": str(e) or "Couldn't load the image"}

    async def save_icon(self, app: str, b64png: str):
        try:
            raw = base64.b64decode(b64png or "", validate=True)
            if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) > 4 * 1024 * 1024:
                return {"ok": False, "error": "Not a PNG"}
            folder = os.path.join(self.data, "icons")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, re.sub(r"[^A-Za-z0-9._-]", "_", str(app)) + ".png")
            with open(path, "wb") as f:
                f.write(raw)
            return {"ok": True, "path": path}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ jobs

    async def queue(self):
        return [self._job_view(j) for j in self.jobs]

    async def install(self, app: str, repair: bool = False):
        app = str(app)
        why = self.lgd.ready()
        if why:
            return {"ok": False, "error": why}
        g = self._game(app)
        inst = (await asyncio.to_thread(self._installed)).get(app)
        if not g and not inst:
            return {"ok": False, "error": "Refresh the library first"}
        if g and not g.get("installable") and not inst:
            return {"ok": False, "error": f"{g['title']} has to be installed through {g.get('third_party') or 'another launcher'}"}
        with self.job_lock:
            if any(j["app"] == app for j in self.jobs):
                return {"ok": True, "jobs": [self._job_view(j) for j in self.jobs]}
            action = "repair" if repair and inst else "update" if inst else "install"
            self.jobs.append({"app": app, "title": (g or inst)["title"], "action": action, "phase": "queued",
                              "done": 0, "total": 0, "speed": 0, "error": "", "cancel": threading.Event()})
        self._emit("epic_job", [self._job_view(j) for j in self.jobs])
        if not self.worker or self.worker.done():
            self.worker = asyncio.get_running_loop().create_task(self._work())
        return {"ok": True, "jobs": [self._job_view(j) for j in self.jobs]}

    async def cancel(self, app: str):
        with self.job_lock:
            for j in self.jobs:
                if j["app"] == str(app):
                    j["cancel"].set()
                    if j["phase"] == "queued":
                        self.jobs.remove(j)
                    break
        jobs = [self._job_view(j) for j in self.jobs]
        self._emit("epic_job", jobs)
        return jobs

    async def discard(self, app: str):
        """Removes what a cancelled download left behind."""
        app = str(app)
        if any(j["app"] == app for j in self.jobs):
            return {"ok": False, "error": "It's still downloading"}
        m = self.meta.get(app)
        roots = [r["path"] for r in self._roots()]
        await asyncio.to_thread(self.lgd.discard, app, m.get("partial", ""), roots)
        self.meta.update(app, partial=None)
        return {"ok": True}

    async def _work(self):
        while True:
            with self.job_lock:
                if not self.jobs:
                    return
                job = self.jobs[0]
            result = None
            try:
                result = await asyncio.to_thread(self._run_job, job)
                job["phase"] = "done"
            except Cancelled:
                job["phase"] = "cancelled"
            except Exception as e:
                job["phase"] = "error"
                job["error"] = str(e) or e.__class__.__name__
                if not isinstance(e, LegendaryError):
                    decky.logger.exception("install failed")
            with self.job_lock:
                if job in self.jobs:
                    self.jobs.remove(job)
            await decky.emit("epic_job_done", {**self._job_view(job), "result": result})
            await decky.emit("epic_job", [self._job_view(j) for j in self.jobs])

    def _run_job(self, job: dict) -> dict:
        app = job["app"]
        job["phase"] = "preparing"
        self._emit("epic_job", [self._job_view(j) for j in self.jobs])
        root = self._root()
        if job["action"] == "install":
            os.makedirs(root, exist_ok=True)

        def progress(phase, done, total, speed, path):
            if path and job["action"] == "install":
                self.meta.update(app, partial=path)
            job.update(phase=phase, done=done, total=total, speed=speed)
            self._emit("epic_job", [self._job_view(j) for j in self.jobs])

        self.lgd.install(app, root if job["action"] == "install" else "", self.settings.data["dlcs"], progress,
                         job["cancel"], repair=job["action"] == "repair")
        self.versions = self.lgd.latest_versions()
        inst = self._installed().get(app)
        if not inst:
            raise LegendaryError("Legendary finished but the game isn't installed. Try again.")
        self.meta.update(app, partial=None)
        return inst

    # ------------------------------------------------------------ installed games

    async def set_shortcut(self, app: str, appid: int):
        self.meta.update(str(app), appid=int(appid or 0))
        return (await asyncio.to_thread(self._installed)).get(str(app))

    async def shortcut_info(self, app: str):
        """What the frontend needs to make or fix the Steam shortcut."""
        inst = (await asyncio.to_thread(self._installed)).get(str(app))
        if not inst:
            return {"ok": False, "error": "Not installed"}
        return {"ok": True, "installed": inst, "options": self.launch_options(str(app))}

    def _prefix_dir(self, appid: int) -> str:
        return os.path.join(steam_root(self.home), "steamapps", "compatdata", str(int(appid)))

    async def uninstall(self, app: str, delete_prefix: bool = False):
        app = str(app)
        if any(j["app"] == app for j in self.jobs):
            return {"ok": False, "error": "Wait for its download to finish or cancel it first"}
        inst = (await asyncio.to_thread(self._installed)).get(app)
        appid = int((inst or {}).get("appid") or self.meta.get(app).get("appid") or 0)

        def run():
            if inst:
                self.lgd.uninstall(app)
            if delete_prefix and appid:
                p = self._prefix_dir(appid)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            try:
                os.unlink(os.path.join(self.data, "icons", re.sub(r"[^A-Za-z0-9._-]", "_", app) + ".png"))
            except OSError:
                pass
        try:
            await asyncio.to_thread(run)
        except Exception as e:
            return _err(e)
        self.meta.drop(app)
        return {"ok": True, "appid": appid}

    async def check_updates(self):
        if not self.lgd.user() or not self.lgd.installed():
            return {"ok": True, "updates": 0, "checked": 0, "installed": {}}
        try:
            self.versions = await asyncio.to_thread(self.lgd.check_updates)
        except Exception as e:
            return _err(e)
        self.last_update_check = time.time()
        inst = await asyncio.to_thread(self._installed)
        return {"ok": True, "updates": sum(1 for r in inst.values() if r["update"]), "checked": len(inst),
                "installed": inst}

    async def saves(self, app: str, direction: str):
        app = str(app)
        inst = (await asyncio.to_thread(self._installed)).get(app)
        if not inst or not inst.get("appid"):
            return {"ok": False, "error": "Add the game to Steam and play it once first"}
        pfx = self._prefix_dir(inst["appid"])
        if not os.path.isfile(os.path.join(pfx, "pfx", "system.reg")):
            return {"ok": False, "error": "Play the game once first so Proton sets up its save folder"}
        if any(j["app"] == app for j in self.jobs):
            return {"ok": False, "error": "Wait for its download to finish"}
        try:
            msg = await asyncio.to_thread(self.lgd.sync_saves, app, pfx, "download" if direction == "download" else "upload")
            return {"ok": True, "message": msg}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ lifecycle

    async def _main(self):
        self.loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(self._install_runtime)
        except Exception:
            decky.logger.exception("couldn't set up the Legendary runtime")
        decky.logger.info("Epic Library ready (idle until opened)")

    async def _unload(self):
        for j in self.jobs:
            j["cancel"].set()
        self.handoff.stop()
        self.device.stop()


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
