"""Amazon Library - Decky backend.

Runs as the normal user (no "root" flag) and does nothing in the background:
- signs this handheld in as an Amazon Games device (tokens kept here, never sent to the UI);
- lists the games on the account, downloads them one at a time when asked, and reports progress
  as events; every file's hash is checked against Amazon's signed manifest;
- keeps a small record of installed games so the frontend can add/update Steam shortcuts
  (Steam shortcuts and artwork are made by the frontend through SteamClient).
Updates are checked only when the library page asks (on open, at most every few hours, or the
Check button).
"""
import asyncio
import base64
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from amzlib import api, install, manifest  # noqa: E402
from amzlib.handoff import Handoff  # noqa: E402
from amzlib.store import Installed, Settings, read_json, write_json  # noqa: E402

CACHE_VERSION = 2                # bump when the cached game shape changes
LIBRARY_TTL = 30 * 60          # owned-games list is refreshed on open after this
UPDATE_TTL = 6 * 3600          # automatic update check on open at most this often
OFFERS_TTL = 6 * 3600
LOGIN_TTL = 20 * 60            # a pending sign-in (PKCE verifier) is good for this long
SDK_PREFIX = "Amazon Games Services/"


def _err(e: BaseException) -> dict:
    if not isinstance(e, (api.ApiError, install.InstallError)):
        decky.logger.error(f"unexpected error: {e!r}")
    return {"ok": False, "error": str(e) or e.__class__.__name__, "status": getattr(e, "status", 0)}


def steam_root(home: str) -> str:
    for p in (".local/share/Steam", ".steam/steam", ".steam/root"):
        full = os.path.join(home, p)
        if os.path.isdir(os.path.join(full, "steamapps")):
            return os.path.realpath(full)
    return os.path.join(home, ".local/share/Steam")


def _fname(game_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(game_id))[:120]


class Plugin:
    def __init__(self):
        self.home = decky.DECKY_USER_HOME
        self.settings = Settings(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"))
        self.installed = Installed(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "installed.json"))
        self.runtime = decky.DECKY_PLUGIN_RUNTIME_DIR
        self.loop = None
        self.jobs: list = []          # queue, first = running
        self.job_lock = threading.Lock()
        self.auth_lock = threading.Lock()
        self.worker = None
        self.handoff = Handoff(self._handoff_code, self._login_url)
        self.update_info: dict = {}   # product id -> {"available": bool, "version": str}
        self.last_update_check = 0.0
        self.offers_cache: dict = {}

    # ------------------------------------------------------------ plumbing

    def _emit(self, event: str, payload) -> None:
        """Thread-safe decky.emit (events reach the frontend only while it listens)."""
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(decky.emit(event, payload), self.loop)
            except RuntimeError:
                pass

    def _root(self) -> str:
        return self.settings.data["root"] or os.path.join(self.home, "Games", "amazon")

    def _public(self) -> dict:
        d = self.settings.public()
        d["root"] = self._root()
        d["home"] = self.home
        return d

    def _token(self) -> str:
        """A valid access token, refreshed when it's about to expire."""
        with self.auth_lock:
            auth = self.settings.data["auth"]
            if not auth.get("refresh_token"):
                raise api.ApiError("Not signed in", 401)
            if api.needs_refresh(auth):
                try:
                    auth = api.refresh(auth)
                except api.ApiError as e:
                    if e.status in (400, 401, 403):
                        self.settings.data["auth"] = {}
                        self.settings.save()
                        self._emit("amazon_signed_out", self._public())
                        raise api.ApiError("Amazon signed this device out. Sign in again.", 401) from None
                    raise
                self.settings.data["auth"] = auth
                self.settings.save()
            return auth["access_token"]

    def _serial(self) -> str:
        return self.settings.data["auth"].get("serial", "")

    def _library_path(self) -> str:
        return os.path.join(self.runtime, "library.json")

    def _manifest_path(self, game_id: str) -> str:
        return os.path.join(self.runtime, "manifests", f"{_fname(game_id)}.proto")

    def _drop_library_cache(self) -> None:
        try:
            os.unlink(self._library_path())
        except OSError:
            pass

    def _installed_view(self, rec: dict) -> dict:
        u = self.update_info.get(rec.get("game_id", "")) or {}
        return {**rec, "present": os.path.isdir(rec.get("dir", "")), "update": bool(u.get("available")),
                "launch": self._launch_options(rec)}

    def _job_view(self, j: dict) -> dict:
        return {k: j[k] for k in ("game_id", "title", "action", "phase", "done", "total", "speed", "error") if k in j}

    def _pending_path(self) -> str:
        return os.path.join(self.runtime, "pending.json")

    @staticmethod
    def _root_of(d: str) -> str:
        return os.path.dirname(os.path.realpath(d))

    def _sdk_dir(self) -> str:
        return os.path.join(self.runtime, "sdk", "Amazon Games Services")

    def _launch_options(self, rec: dict) -> str:
        """Steam launch options: the env vars Amazon's Fuel SDK reads, then the game's own arguments."""
        name = (self.settings.data["auth"].get("user") or {}).get("name", "")
        env = {
            "AMAZON_GAMES_FUEL_ENTITLEMENT_ID": rec.get("entitlement", ""),
            "AMAZON_GAMES_FUEL_PRODUCT_SKU": rec.get("sku", ""),
            "AMAZON_GAMES_FUEL_DISPLAY_NAME": re.sub(r"[\"'`$\\]", "", name)[:40],
        }
        sdk = self._sdk_dir()
        if os.path.isdir(sdk):
            env["FUEL_DIR"] = install.win_path(os.path.join(sdk, "Legacy"))
            env["AMAZON_GAMES_SDK_PATH"] = install.win_path(os.path.join(sdk, "AmazonGamesSDK"))
        parts = [f'{k}="{v}"' for k, v in env.items() if v]
        parts.append("%command%")
        if rec.get("args"):
            parts.append(rec["args"])
        return " ".join(parts)

    # ------------------------------------------------------------ settings / sign-in

    def _login(self, fresh: bool = False) -> dict:
        lg = self.settings.data["login"]
        if fresh or not lg.get("verifier") or time.time() - float(lg.get("at", 0)) > LOGIN_TTL:
            lg = api.new_login()
            self.settings.data["login"] = lg
            self.settings.save()
        return lg

    def _login_url(self) -> str:
        return self._login()["url"]

    def _finish_login(self, text: str) -> tuple:
        code = api.code_from(text)
        if not code:
            return False, "That isn't the amazon.com address with the sign-in code. Copy the whole address after signing in.", None
        lg = self.settings.data["login"]
        if not lg.get("verifier"):
            return False, "This sign-in expired. Scan the code again to start over.", None
        try:
            auth = api.register(code, lg)
        except api.ApiError as e:
            return False, f"{e} Codes only work once and for a few minutes: open the sign-in link again.", None
        self.settings.data["auth"] = auth
        self.settings.data["login"] = {}
        self.settings.save()
        self._drop_library_cache()
        self.offers_cache = {}
        name = auth["user"].get("name") or "your Amazon account"
        decky.logger.info("signed in to Amazon Games")
        return True, f"Signed in as {name}.", auth["user"]

    def _handoff_code(self, text: str) -> tuple:
        ok, msg, _user = self._finish_login(text)
        if ok:
            self._emit("amazon_signed_in", self._public())
        return ok, msg

    async def settings_get(self):
        return self._public()

    async def set_code(self, text: str):
        ok, msg, _ = await asyncio.to_thread(self._finish_login, text)
        return {"ok": ok, "message": msg, "settings": self._public()}

    async def sign_out(self):
        auth = self.settings.data["auth"]
        if auth.get("access_token"):
            await asyncio.to_thread(api.deregister, auth)
        self.settings.data["auth"] = {}
        self.settings.data["login"] = {}
        self.settings.save()
        self._drop_library_cache()
        self.update_info.clear()
        self.offers_cache = {}
        return self._public()

    async def handoff_start(self):
        def run():
            self._login()
            return self.handoff.start()
        return await asyncio.to_thread(run)

    async def handoff_status(self):
        return {**self.handoff.status(), "signedIn": bool(self._public().get("signedIn"))}

    async def handoff_stop(self):
        await asyncio.to_thread(self.handoff.stop)
        return True

    async def set_options(self, opts: dict):
        s = self.settings.data
        if isinstance(opts.get("tool"), str):
            s["tool"] = opts["tool"][:120]
        if isinstance(opts.get("root"), str):
            # /home is a symlink to /var/home on Bazzite, so compare resolved paths.
            want = os.path.realpath(opts["root"]) if opts["root"] else ""
            match = next((r["path"] for r in self._roots() if os.path.realpath(r["path"]) == want), None)
            if want and not match:
                return {"ok": False, "error": "That folder isn't one of the offered locations"}
            internal = os.path.realpath(os.path.join(self.home, "Games", "amazon"))
            s["root"] = "" if not want or want == internal else match
        self.settings.save()
        return {"ok": True, "settings": self._public()}

    def _roots(self) -> list:
        """Internal storage plus every writable removable drive (SD card, USB)."""
        out = [{"path": os.path.join(self.home, "Games", "amazon"), "label": "Internal"}]
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
                out.append({"path": os.path.join(m, "Games", "amazon"), "label": f"Drive · {n}"})
        cur = self._root()
        if not any(os.path.realpath(r["path"]) == os.path.realpath(cur) for r in out):
            out.append({"path": cur, "label": "Current (not mounted)" if not os.path.isdir(os.path.dirname(cur)) else "Current"})
        for r in out:
            r["free"] = install.free_bytes(r["path"])
        return out

    async def roots(self):
        return await asyncio.to_thread(self._roots)

    # ------------------------------------------------------------ library

    def _library(self, refresh: bool) -> dict:
        token = self._token()
        cache = read_json(self._library_path(), {})
        uid = (self.settings.data["auth"].get("user") or {}).get("id")
        fresh = cache.get("user") == uid and cache.get("v") == CACHE_VERSION and time.time() - float(cache.get("at", 0)) < LIBRARY_TTL
        if refresh or not fresh or not isinstance(cache.get("games"), list):
            games = api.entitlements(token, self._serial())
            cache = {"at": time.time(), "user": uid, "v": CACHE_VERSION, "games": games}
            write_json(self._library_path(), cache)
        return {"games": cache["games"], "at": cache["at"]}

    async def library(self, refresh: bool = False):
        try:
            lib = await asyncio.to_thread(self._library, bool(refresh))
        except Exception as e:
            return _err(e)
        inst = {k: self._installed_view(v) for k, v in self.installed.games.items()}
        due = time.time() - self.last_update_check > UPDATE_TTL and bool(inst)
        return {"ok": True, **lib, "installed": inst, "jobs": [self._job_view(j) for j in self.jobs],
                "updatesDue": due}

    def _find_game(self, game_id: str) -> dict | None:
        cache = read_json(self._library_path(), {})
        for g in cache.get("games") or []:
            if g.get("id") == game_id:
                return g
        rec = self.installed.get(game_id)
        if rec:
            return {"id": game_id, "entitlement": rec.get("entitlement", ""), "sku": rec.get("sku", ""),
                    "title": rec.get("title", ""), "icon": rec.get("icon", ""), "cover": rec.get("cover", ""),
                    "background": rec.get("background", ""), "logo": rec.get("logo", ""), "short": "",
                    "developer": "", "publisher": "", "genres": [], "released": "", "screenshot": "", "added": "",
                    "description": "", "screenshots": [], "modes": [], "rating": "", "website": ""}
        return None

    async def game(self, game_id: str):
        g = self._find_game(str(game_id))
        if not g:
            return {"ok": False, "error": "This game isn't in your Amazon library (refresh the library?)"}
        rec = self.installed.get(game_id)
        return {"ok": True, "game": g, "installed": self._installed_view(rec) if rec else None}

    async def offers(self, refresh: bool = False):
        c = self.offers_cache
        if not refresh and c.get("items") is not None and time.time() - c.get("at", 0) < OFFERS_TTL:
            return {"ok": True, "items": c["items"], "claims": api.CLAIMS_URL}
        try:
            token = await asyncio.to_thread(self._token)
            items = await asyncio.to_thread(api.prime_offers, token)
        except Exception as e:
            r = _err(e)
            r["claims"] = api.CLAIMS_URL
            return r
        self.offers_cache = {"at": time.time(), "items": items}
        return {"ok": True, "items": items, "claims": api.CLAIMS_URL}

    async def art(self, game_id: str):
        """Cover, background and logo as base64 for the canvas (never tainted that way)."""
        g = self._find_game(str(game_id))
        if not g:
            return {"ok": False, "error": "Unknown game"}

        def get(url):
            try:
                data, ext = api.image(url)
                return {"data": base64.b64encode(data).decode("ascii"), "ext": ext}
            except Exception:
                return None
        cover = await asyncio.to_thread(get, g.get("cover") or g.get("icon"))
        if not cover and g.get("icon") and g.get("cover") != g.get("icon"):
            cover = await asyncio.to_thread(get, g.get("icon"))
        bg = await asyncio.to_thread(get, g.get("background")) if g.get("background") else None
        logo = await asyncio.to_thread(get, g.get("logo")) if g.get("logo") else None
        if not cover and not bg:
            return {"ok": False, "error": "Amazon has no artwork for this game"}
        return {"ok": True, "cover": cover or bg, "background": bg, "logo": logo, "title": g.get("title", "")}

    async def save_icon(self, game_id: str, b64png: str):
        try:
            raw = base64.b64decode(b64png or "", validate=True)
            if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) > 4 * 1024 * 1024:
                return {"ok": False, "error": "Not a PNG"}
            folder = os.path.join(self.runtime, "icons")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{_fname(game_id)}.png")
            with open(path, "wb") as f:
                f.write(raw)
            return {"ok": True, "path": path}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ jobs

    async def queue(self):
        return [self._job_view(j) for j in self.jobs]

    async def install(self, game_id: str, repair: bool = False):
        game_id = str(game_id)
        g = self._find_game(game_id)
        if not g or not g.get("entitlement"):
            return {"ok": False, "error": "Refresh the library first so this game's details are known"}
        with self.job_lock:
            if any(j["game_id"] == game_id for j in self.jobs):
                return {"ok": True, "queued": True, "jobs": [self._job_view(j) for j in self.jobs]}
            prev = self.installed.get(game_id)
            action = "repair" if repair and prev else "update" if prev else "install"
            self.jobs.append({"game_id": game_id, "title": g["title"], "game": g, "action": action, "phase": "queued",
                              "done": 0, "total": 0, "speed": 0, "error": "", "cancel": threading.Event()})
        self._emit("amazon_job", [self._job_view(j) for j in self.jobs])
        if not self.worker or self.worker.done():
            self.worker = asyncio.get_running_loop().create_task(self._work())
        return {"ok": True, "queued": True, "jobs": [self._job_view(j) for j in self.jobs]}

    async def cancel(self, game_id: str):
        with self.job_lock:
            for j in self.jobs:
                if j["game_id"] == str(game_id):
                    j["cancel"].set()
                    if j["phase"] == "queued":
                        self.jobs.remove(j)
                    break
        jobs = [self._job_view(j) for j in self.jobs]
        self._emit("amazon_job", jobs)
        return jobs

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
            except install.Cancelled:
                job["phase"] = "cancelled"
            except Exception as e:
                job["phase"] = "error"
                job["error"] = str(e) or e.__class__.__name__
                if not isinstance(e, (api.ApiError, install.InstallError)):
                    decky.logger.exception("install failed")
            with self.job_lock:
                if job in self.jobs:
                    self.jobs.remove(job)
            await decky.emit("amazon_job_done", {**self._job_view(job), "result": result})
            await decky.emit("amazon_job", [self._job_view(j) for j in self.jobs])

    def _progress(self, job: dict, phase: str, done: int = 0, total: int = 0):
        now = time.monotonic()
        if phase == "downloading":
            if not job.get("_t0"):
                job["_t0"], job["_d0"] = now, done
            dt = now - job["_t0"]
            job["speed"] = int((done - job["_d0"]) / dt) if dt > 1 else 0
        job.update(phase=phase, done=done, total=total)
        self._emit("amazon_job", [self._job_view(j) for j in self.jobs])

    def _ensure_sdk(self, cancel: threading.Event) -> None:
        """The Fuel / Amazon Games SDK DLLs some games load (a few MB, fetched once)."""
        if os.path.isdir(self._sdk_dir()):
            return
        try:
            ch = api.sdk_channel()
            files, _raw = install.fetch_manifest(ch["url"])
            want = [f for f in files if f["path"].startswith(SDK_PREFIX)
                    and ("FuelSDK_x64.dll" in f["path"] or "AmazonGamesSDK_" in f["path"])]
            if not want:
                return
            tmp = os.path.join(self.runtime, ".sdk-tmp")
            install.rmtree(tmp)
            install.sync_files(ch["url"], want, tmp, cancel, lambda d, t: None, verify_existing=False)
            os.makedirs(os.path.join(self.runtime, "sdk"), exist_ok=True)
            os.replace(os.path.join(tmp, SDK_PREFIX.rstrip("/")), self._sdk_dir())
            install.rmtree(tmp)
        except install.Cancelled:
            raise
        except Exception as e:
            decky.logger.warning(f"Amazon Games SDK not fetched ({e}); games that need it may not start")

    def _run_job(self, job: dict) -> dict:
        g = job["game"]
        gid = job["game_id"]
        cancel = job["cancel"]
        prev = self.installed.get(gid)
        self._progress(job, "preparing")
        token = self._token()
        dl = api.game_download(token, g["entitlement"])
        files, raw = install.fetch_manifest(dl["url"])
        if not files:
            raise install.InstallError("Amazon's download for this game is empty")
        self._ensure_sdk(cancel)

        root = os.path.realpath(prev["root"]) if prev and prev.get("root") else self._root()
        final = prev["dir"] if prev and prev.get("dir") and install.inside(root, prev["dir"]) else \
            os.path.join(root, install.slug(g["title"], gid))
        old_files = None
        if prev and job["action"] == "update" and os.path.isdir(final):
            try:
                with open(self._manifest_path(gid), "rb") as f:
                    old_files = manifest.parse(f.read())
            except (OSError, manifest.ManifestError):
                old_files = None      # no old manifest: compare every file against the disk
        probe = root
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        if root.startswith("/run/media/") and os.path.realpath(probe) in ("/run/media", f"/run/media/{os.path.basename(self.home)}"):
            raise install.InstallError("The drive this game was installed on isn't inserted")
        fetch, remove = manifest.compare(files, old_files)
        need = sum(f["size"] for f in fetch)
        os.makedirs(root, exist_ok=True)
        if install.free_bytes(root) < need + 256 * 1024 * 1024:
            raise install.InstallError(f"Not enough free space in {root} (about {need // (1024 * 1024)} MB needed)")

        fresh = not os.path.isdir(final)
        os.makedirs(final, exist_ok=True)
        write_json(self._pending_path(), [final])
        job["_t0"] = 0
        self._progress(job, "downloading", 0, need)
        try:
            install.sync_files(dl["url"], fetch, final, cancel, lambda d, t: self._progress(job, "downloading", d, t))
        except install.Cancelled:
            if fresh and not prev:
                install.rmtree(final)     # a cancelled first install leaves nothing behind
            raise
        finally:
            write_json(self._pending_path(), [])
        if remove:
            self._progress(job, "finishing")
            install.remove_files(final, remove)
        os.makedirs(os.path.dirname(self._manifest_path(gid)), exist_ok=True)
        with open(self._manifest_path(gid), "wb") as f:
            f.write(raw)

        # What Steam launches: fuel.json first; else keep the user's pick; else the best .exe.
        self._progress(job, "finishing")
        fu = install.fuel(final)
        exe, args, cwd = "", "", final
        if prev and prev.get("exe") and prev.get("picked") and prev.get("dir"):
            rel = os.path.relpath(prev["exe"], prev["dir"]) if install.inside(prev["dir"], prev["exe"]) else ""
            if rel and os.path.isfile(os.path.join(final, rel)):
                exe, args, cwd = os.path.join(final, rel), prev.get("args", ""), os.path.dirname(os.path.join(final, rel))
        if not exe and fu and os.path.isfile(fu["exe"]):
            exe, args, cwd = fu["exe"], install.quote_args(fu["args"]), fu["cwd"]
        if not exe:
            cands = install.scan(final, g["title"])
            if cands:
                exe, cwd = cands[0]["path"], os.path.dirname(cands[0]["path"])
        if not exe:
            raise install.InstallError("Downloaded, but no game executable was found in it")
        rec = {
            "game_id": gid, "entitlement": g["entitlement"], "sku": g.get("sku", ""), "title": g["title"],
            "icon": g.get("icon", ""), "cover": g.get("cover", ""), "background": g.get("background", ""),
            "logo": g.get("logo", ""), "version": dl["version"], "root": root, "dir": final, "exe": exe,
            "args": args, "cwd": cwd, "picked": bool(prev and prev.get("picked") and exe == prev.get("exe")),
            "post_install": int(fu.get("post", 0)) if fu else 0, "fuel": bool(fu),
            "appid": (prev or {}).get("appid", 0), "installed_at": int(time.time()),
            "size": sum(f["size"] for f in files),
        }
        self.installed.put(gid, rec)
        self.update_info.pop(gid, None)
        return self._installed_view(rec)

    # ------------------------------------------------------------ installed games

    async def set_shortcut(self, game_id: str, appid: int):
        rec = self.installed.get(game_id)
        if not rec:
            return None
        rec["appid"] = int(appid or 0)
        self.installed.put(game_id, rec)
        return self._installed_view(rec)

    def _prefix_dir(self, appid: int) -> str:
        return os.path.join(steam_root(self.home), "steamapps", "compatdata", str(int(appid)))

    async def executables(self, game_id: str):
        rec = self.installed.get(game_id)
        if not rec:
            return []

        def run():
            out = install.scan(rec["dir"], rec["title"])
            fu = install.fuel(rec["dir"])
            if fu:
                for c in out:
                    if os.path.realpath(c["path"]) == os.path.realpath(fu["exe"]):
                        c["score"] += 1000
                        c["fuel"] = True
            out = [c for c in out if not install.HELPERS.search(os.path.basename(c["path"]).lower()) or c["path"] == rec["exe"]]
            out.sort(key=lambda c: c["score"], reverse=True)
            return out[:40]
        return await asyncio.to_thread(run)

    async def set_exe(self, game_id: str, path: str):
        rec = self.installed.get(game_id)
        if not rec:
            return {"ok": False, "error": "Not installed"}
        path = os.path.realpath(path or "")
        if not os.path.isfile(path) or not install.inside(rec["dir"], path) or not path.lower().endswith(".exe"):
            return {"ok": False, "error": "Pick a .exe inside the game's folder"}
        fu = install.fuel(rec["dir"])
        is_fuel = bool(fu) and os.path.realpath(fu["exe"]) == path
        rec["exe"] = path
        rec["args"] = install.quote_args(fu["args"]) if is_fuel else ""
        rec["cwd"] = fu["cwd"] if is_fuel else os.path.dirname(path)
        rec["picked"] = not is_fuel
        self.installed.put(game_id, rec)
        return {"ok": True, "installed": self._installed_view(rec)}

    async def uninstall(self, game_id: str, delete_prefix: bool = False):
        game_id = str(game_id)
        rec = self.installed.get(game_id)
        if not rec:
            return {"ok": True, "appid": 0}
        if any(j["game_id"] == game_id for j in self.jobs):
            return {"ok": False, "error": "Wait for its download to finish or cancel it first"}
        d = rec.get("dir", "")
        root = rec.get("root", "")

        def run():
            # Only ever delete a folder this plugin made: <root>/<name>-<id suffix>.
            if d and root and install.inside(root, d) and os.path.realpath(d) != os.path.realpath(root) \
                    and os.path.basename(d.rstrip("/")).endswith(f"-{install.suffix(game_id)}"):
                install.rmtree(d)
            if delete_prefix and rec.get("appid"):
                p = self._prefix_dir(rec["appid"])
                if os.path.isdir(p):
                    install.rmtree(p)
            for f in (self._manifest_path(game_id), os.path.join(self.runtime, "icons", f"{_fname(game_id)}.png")):
                try:
                    os.unlink(f)
                except OSError:
                    pass
        try:
            await asyncio.to_thread(run)
        except Exception as e:
            return _err(e)
        self.installed.drop(game_id)
        self.update_info.pop(game_id, None)
        return {"ok": True, "appid": int(rec.get("appid") or 0)}

    async def check_updates(self):
        recs = list(self.installed.games.values())
        if not recs or not self.settings.data["auth"].get("refresh_token"):
            return {"ok": True, "updates": 0, "checked": 0, "installed": {}}

        def run():
            token = self._token()
            ids = [r["game_id"] for r in recs]
            live = {}
            for i in range(0, len(ids), 50):
                live.update(api.live_versions(token, ids[i:i + 50]))
            return live
        try:
            live = await asyncio.to_thread(run)
        except Exception as e:
            return _err(e)
        n = 0
        for r in recs:
            v = live.get(r["game_id"])
            if not v:
                continue
            avail = bool(r.get("version")) and v != r.get("version")
            self.update_info[r["game_id"]] = {"available": avail, "version": v}
            n += 1 if avail else 0
        self.last_update_check = time.time()
        return {"ok": True, "updates": n, "checked": len(recs),
                "installed": {k: self._installed_view(v) for k, v in self.installed.games.items()}}

    async def installed_list(self):
        return {k: self._installed_view(v) for k, v in self.installed.games.items()}

    # ------------------------------------------------------------ lifecycle

    async def _main(self):
        self.loop = asyncio.get_running_loop()

        def tidy():
            # Half-written files from a download that was cut off (power loss, Decky restart).
            for d in read_json(self._pending_path(), []):
                if isinstance(d, str) and os.path.isdir(d) and install.inside(self._root_of(d), d):
                    for dp, _dn, fn in os.walk(d):
                        for f in fn:
                            if f.endswith(".part"):
                                try:
                                    os.unlink(os.path.join(dp, f))
                                except OSError:
                                    pass
            write_json(self._pending_path(), [])
            install.rmtree(os.path.join(self.runtime, ".sdk-tmp"))
        await asyncio.to_thread(tidy)
        decky.logger.info("Amazon Library ready (idle until opened)")

    async def _unload(self):
        for j in self.jobs:
            j["cancel"].set()
        self.handoff.stop()
