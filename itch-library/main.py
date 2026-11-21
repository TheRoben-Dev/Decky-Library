"""Itch Library - Decky backend.

Runs as the normal user (no "root" flag) and does nothing in the background:
- talks to api.itch.io with the user's own API key (kept here, never sent to the UI);
- downloads and unpacks games one at a time, only when asked, and reports progress as events;
- keeps a small record of installed games so the frontend can add/update Steam shortcuts
  (Steam shortcuts and artwork are made by the frontend through SteamClient).
Updates are checked only when the library page asks for it (on open, at most every few hours,
or the Check button).
"""
import asyncio
import base64
import concurrent.futures
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from itchlib import api, browse, install  # noqa: E402
from itchlib.handoff import Handoff  # noqa: E402
from itchlib.store import Installed, Settings, read_json, write_json  # noqa: E402

KEY_RE = re.compile(r"[A-Za-z0-9_\-]{20,80}")
LIBRARY_TTL = 30 * 60          # owned-games list is refreshed on open after this
UPDATE_TTL = 6 * 3600          # automatic update check on open at most this often
KEY_FILES = ("key.txt",)       # in the plugin's settings folder
DESKTOP_KEY_FILES = ("itch-key.txt", "itch-api-key.txt")


def _err(e: BaseException) -> dict:
    if not isinstance(e, (api.ApiError, install.InstallError)):
        decky.logger.error(f"unexpected error: {e!r}")
    return {"ok": False, "error": str(e) or e.__class__.__name__, "status": getattr(e, "status", 0),
            "retry_after": getattr(e, "retry_after", 0), "detail": getattr(e, "detail", "")}


def steam_root(home: str) -> str:
    for p in (".local/share/Steam", ".steam/steam", ".steam/root"):
        full = os.path.join(home, p)
        if os.path.isdir(os.path.join(full, "steamapps")):
            return os.path.realpath(full)
    return os.path.join(home, ".local/share/Steam")


class Plugin:
    def __init__(self):
        self.home = decky.DECKY_USER_HOME
        self.settings = Settings(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"))
        self.installed = Installed(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "installed.json"))
        self.runtime = decky.DECKY_PLUGIN_RUNTIME_DIR
        self.loop = None
        self.jobs: list = []          # queue, first = running
        self.job_lock = threading.Lock()
        self.worker = None
        self.handoff = Handoff(self._handoff_key)
        self.update_info: dict = {}   # game id -> {"available": bool, "upload": {...}}
        self.last_update_check = 0.0
        self.seen: dict = {}          # store games opened from Browse/Search (not owned), by id

    # ------------------------------------------------------------ plumbing

    def _emit(self, event: str, payload) -> None:
        """Thread-safe decky.emit (events reach the frontend only while it listens)."""
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(decky.emit(event, payload), self.loop)
            except RuntimeError:
                pass

    def _key(self) -> str:
        return self.settings.data["key"]

    def _root(self) -> str:
        return self.settings.data["root"] or os.path.join(self.home, "Games", "itch")

    def _public(self) -> dict:
        d = self.settings.public()
        d["root"] = self._root()
        d["home"] = self.home
        return d

    def _validate_key(self, key: str) -> tuple:
        key = re.sub(r"\s+", "", key or "")
        if not KEY_RE.fullmatch(key):
            return False, "That doesn't look like an itch.io API key.", None
        try:
            user = api.profile(key)
        except api.ApiError as e:
            if e.status in (400, 401, 403):
                return False, "itch.io rejected that key. Copy it again from Settings → API keys.", None
            return False, str(e), None
        self.settings.data["key"] = key
        self.settings.data["user"] = {"id": user["id"], "username": user["username"], "name": user["name"]}
        self.settings.save()
        self._drop_library_cache()
        decky.logger.info(f"signed in as {user['username']}")
        return True, f"Signed in as {user['name'] or user['username']}.", user

    def _handoff_key(self, key: str) -> tuple:
        ok, msg, _user = self._validate_key(key)
        if ok:
            self._emit("itch_signed_in", self._public())
        return ok, msg

    def _import_key_files(self) -> str:
        """A key in ~/homebrew/settings/Itch Library/key.txt or ~/Desktop/itch-key.txt (easy to
        make in Desktop Mode) is picked up once and the file removed."""
        paths = [os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, n) for n in KEY_FILES]
        paths += [os.path.join(self.home, "Desktop", n) for n in DESKTOP_KEY_FILES]
        for p in paths:
            try:
                with open(p, encoding="utf-8") as f:
                    raw = f.read(512)
            except OSError:
                continue
            ok, msg, _ = self._validate_key(raw)
            if ok:
                try:
                    os.unlink(p)
                except OSError:
                    pass
                return msg
            decky.logger.warning(f"key file {p}: {msg}")
            return f"{os.path.basename(p)}: {msg}"
        return ""

    def _library_path(self) -> str:
        return os.path.join(self.runtime, "library.json")

    def _drop_library_cache(self) -> None:
        try:
            os.unlink(self._library_path())
        except OSError:
            pass

    def _installed_view(self, rec: dict) -> dict:
        gid = str(rec.get("game_id"))
        u = self.update_info.get(gid) or {}
        return {**rec, "present": os.path.isdir(rec.get("dir", "")), "update": bool(u.get("available")),
                "update_name": (u.get("upload") or {}).get("name", "")}

    def _job_view(self, j: dict) -> dict:
        return {k: j[k] for k in ("game_id", "title", "action", "phase", "done", "total", "speed", "error") if k in j}

    # ------------------------------------------------------------ settings / sign-in

    async def settings_get(self):
        msg = await asyncio.to_thread(self._import_key_files)
        return {**self._public(), "imported": msg}

    async def set_key(self, key: str):
        ok, msg, _ = await asyncio.to_thread(self._validate_key, key)
        return {"ok": ok, "message": msg, "settings": self._public()}

    async def sign_out(self):
        self.settings.data["key"] = ""
        self.settings.data["user"] = {}
        self.settings.save()
        self._drop_library_cache()
        self.update_info.clear()
        return self._public()

    async def handoff_start(self):
        return await asyncio.to_thread(self.handoff.start)

    async def handoff_status(self):
        return {**self.handoff.status(), "signedIn": bool(self.settings.data.get("key"))}

    async def handoff_stop(self):
        await asyncio.to_thread(self.handoff.stop)
        return True

    async def set_options(self, opts: dict):
        s = self.settings.data
        if opts.get("prefer") in ("linux", "windows"):
            s["prefer"] = opts["prefer"]
        if isinstance(opts.get("tool"), str):
            s["tool"] = opts["tool"][:120]
        for k in ("show_all", "keep_downloads", "adult"):
            if k in opts:
                s[k] = bool(opts[k])
        if isinstance(opts.get("root"), str):
            # /home is a symlink to /var/home on Bazzite, so compare resolved paths.
            want = os.path.realpath(opts["root"]) if opts["root"] else ""
            match = next((r["path"] for r in self._roots() if os.path.realpath(r["path"]) == want), None)
            if want and not match:
                return {"ok": False, "error": "That folder isn't one of the offered locations"}
            internal = os.path.realpath(os.path.join(self.home, "Games", "itch"))
            s["root"] = "" if not want or want == internal else match
        self.settings.save()
        return {"ok": True, "settings": self._public()}

    def _roots(self) -> list:
        """Internal storage plus every writable removable drive (SD card, USB)."""
        out = [{"path": os.path.join(self.home, "Games", "itch"), "label": "Internal"}]
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
                out.append({"path": os.path.join(m, "Games", "itch"), "label": f"Drive · {n}"})
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
        key = self._key()
        if not key:
            raise api.ApiError("Not signed in", 401)
        cache = read_json(self._library_path(), {})
        uid = self.settings.data["user"].get("id")
        fresh = cache.get("user") == uid and time.time() - float(cache.get("at", 0)) < LIBRARY_TTL
        if refresh or not fresh or not isinstance(cache.get("games"), list):
            games = api.owned(key)
            cache = {"at": time.time(), "user": uid, "games": games}
            write_json(self._library_path(), cache)
        games = cache["games"]
        if not self.settings.data["show_all"]:
            games = [g for g in games if g.get("classification") in api.GAME_CLASSES]
        return {"games": games, "at": cache["at"]}

    async def library(self, refresh: bool = False):
        try:
            lib = await asyncio.to_thread(self._library, bool(refresh))
        except Exception as e:
            return _err(e)
        inst = {k: self._installed_view(v) for k, v in self.installed.games.items()}
        due = time.time() - self.last_update_check > UPDATE_TTL and bool(inst)
        return {"ok": True, **lib, "installed": inst, "jobs": [self._job_view(j) for j in self.jobs],
                "updatesDue": due}

    def _owned(self, game_id: int) -> dict | None:
        cache = read_json(self._library_path(), {})
        for g in cache.get("games") or []:
            if g.get("id") == int(game_id):
                return g
        return None

    def _find_game(self, game_id: int) -> dict | None:
        g = self._owned(game_id)
        if g:
            return g
        rec = self.installed.get(game_id)
        if rec:
            return {"id": int(game_id), "title": rec.get("title", ""), "key": rec.get("key", 0),
                    "still": rec.get("cover", ""), "cover": rec.get("cover", ""), "short": "", "url": rec.get("url", ""),
                    "author": "", "platforms": [], "classification": "", "min_price": rec.get("min_price", 0)}
        return self.seen.get(int(game_id))

    @staticmethod
    def _allowed(g: dict, owned: bool, u: dict) -> bool:
        """Owned or free games: any build. Paid games you don't own: only their free demos."""
        return api.installable(u) and (owned or not g.get("min_price") or u["demo"])

    async def game(self, game_id: int):
        key = self._key()
        owned_g = self._owned(game_id)
        g = owned_g or self._find_game(game_id)
        if not owned_g:
            # Not in the library: look it up as a store page (price, platforms, cover).
            try:
                info = await asyncio.to_thread(api.game_detail, key, int(game_id))
                info["key"] = (g or {}).get("key", 0)
                g = {**(g or {}), **info}
                self.seen[int(game_id)] = g
            except Exception as e:
                if not g:
                    return _err(e)
        owned = bool(owned_g) or bool(g.get("key"))
        rec = self.installed.get(game_id)
        base = {"game": g, "owned": owned, "installed": self._installed_view(rec) if rec else None}
        try:
            ups = await asyncio.to_thread(api.uploads, key, g["id"], g.get("key", 0))
        except Exception as e:
            r = _err(e)
            r.update(base)
            return r
        usable = [u for u in ups if self._allowed(g, owned, u)]
        best = api.pick_upload(usable, self.settings.data["prefer"])
        for u in ups:
            u.pop("targets", None)
            u["usable"] = self._allowed(g, owned, u)
        return {"ok": True, **base, "uploads": ups, "best": best["id"] if best else 0, "usable": len(usable)}

    # ------------------------------------------------------------ store

    async def browse(self, opts: dict):
        o = opts if isinstance(opts, dict) else {}
        try:
            tags = o.get("tags") or []
            more = {k: str(o.get(k) or "") for k in ("released", "duration", "multiplayer", "accessibility", "engine")}
            more.update(tags=[str(t) for t in tags][:3] if isinstance(tags, list) else [],
                        demo=bool(o.get("demo")), adult=bool(self.settings.data.get("adult")))
            args = (str(o.get("sort", "")), str(o.get("price", "")), str(o.get("genre", "")),
                    str(o.get("controller", "gamepad")), str(o.get("platform", "")), int(o.get("page", 1) or 1))
            try:
                res = await asyncio.to_thread(browse.browse, *args, **more)
            except browse.BrowseError as e:
                if e.status not in browse.BLOCKED or not self.settings.data.get("key"):
                    raise
                decky.logger.warning(f"browse feed blocked ({e.status}: {e.detail}); using API search instead")
                res = await asyncio.to_thread(browse.browse_via_api, self._key(), *args, **more)
                res["detail"] = e.detail
            return {"ok": True, **res}
        except Exception as e:
            return _err(e)

    async def search(self, query: str, page: int = 1):
        try:
            res = await asyncio.to_thread(browse.search, self._key(), query, int(page or 1))
            return {"ok": True, **res}
        except Exception as e:
            return _err(e)

    async def resolve(self, url: str):
        """Game id for a Browse item (feed items only carry the page URL)."""
        try:
            gid = await asyncio.to_thread(browse.resolve, url)
            return {"ok": True, "id": gid}
        except Exception as e:
            return _err(e)

    async def cover(self, game_id: int):
        g = self._find_game(game_id)
        if not g:
            return {"ok": False, "error": "Unknown game"}
        try:
            data, ext = await asyncio.to_thread(api.cover, g.get("still") or g.get("cover") or "")
            return {"ok": True, "data": base64.b64encode(data).decode("ascii"), "ext": ext}
        except Exception as e:
            return _err(e)

    async def save_icon(self, game_id: int, b64png: str):
        try:
            raw = base64.b64decode(b64png or "", validate=True)
            if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) > 4 * 1024 * 1024:
                return {"ok": False, "error": "Not a PNG"}
            folder = os.path.join(self.runtime, "icons")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{int(game_id)}.png")
            with open(path, "wb") as f:
                f.write(raw)
            return {"ok": True, "path": path}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ jobs

    async def queue(self):
        return [self._job_view(j) for j in self.jobs]

    async def install(self, game_id: int, upload_id: int = 0):
        g = self._find_game(game_id)
        if not g:
            return {"ok": False, "error": "Open the game first so its details are known"}
        with self.job_lock:
            if any(j["game_id"] == int(game_id) for j in self.jobs):
                return {"ok": True, "queued": True, "jobs": [self._job_view(j) for j in self.jobs]}
            action = "update" if self.installed.get(game_id) else "install"
            self.jobs.append({"game_id": int(game_id), "title": g["title"], "game": g, "upload_id": int(upload_id or 0),
                              "action": action, "phase": "queued", "done": 0, "total": 0, "speed": 0, "error": "",
                              "cancel": threading.Event()})
        self._emit("itch_job", [self._job_view(j) for j in self.jobs])
        if not self.worker or self.worker.done():
            self.worker = asyncio.get_running_loop().create_task(self._work())
        return {"ok": True, "queued": True, "jobs": [self._job_view(j) for j in self.jobs]}

    async def cancel(self, game_id: int):
        with self.job_lock:
            for j in self.jobs:
                if j["game_id"] == int(game_id):
                    j["cancel"].set()
                    if j["phase"] == "queued":
                        self.jobs.remove(j)
                    break
        jobs = [self._job_view(j) for j in self.jobs]
        self._emit("itch_job", jobs)
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
            await decky.emit("itch_job_done", {**self._job_view(job), "result": result})
            await decky.emit("itch_job", [self._job_view(j) for j in self.jobs])

    def _progress(self, job: dict, phase: str, done: int = 0, total: int = 0):
        now = time.monotonic()
        if phase == "downloading" and job.get("_t0"):
            dt = now - job["_t0"]
            job["speed"] = int(done / dt) if dt > 0.5 else 0
        job.update(phase=phase, done=done, total=total)
        self._emit("itch_job", [self._job_view(j) for j in self.jobs])

    def _run_job(self, job: dict) -> dict:
        key = self._key()
        g = job["game"]
        gid = job["game_id"]
        cancel = job["cancel"]
        prev = self.installed.get(gid)
        self._progress(job, "preparing")
        owned = bool(self._owned(gid)) or bool(g.get("key"))
        ups = [u for u in api.uploads(key, gid, g.get("key", 0)) if self._allowed(g, owned, u)]
        up = None
        want = job["upload_id"] or (prev or {}).get("upload_id", 0)
        if want:
            up = next((u for u in ups if u["id"] == want and api.installable(u)), None)
        if not up and prev:
            # The developer replaced the upload: take the best one for the same platform.
            same = [u for u in ups if api.installable(u) and prev.get("kind") in u["platforms"]]
            up = api.pick_upload(same or ups, prev.get("kind") or self.settings.data["prefer"])
        if not up:
            up = api.pick_upload(ups, self.settings.data["prefer"])
        if not up:
            raise install.InstallError("No Linux or Windows build to install")

        root = os.path.realpath(prev["root"]) if prev and prev.get("root") else self._root()
        os.makedirs(root, exist_ok=True)
        need = int(up["size"] * 2.2) + 256 * 1024 * 1024
        if up["size"] and install.free_bytes(root) < need:
            raise install.InstallError(f"Not enough free space in {root} (about {need // (1024 * 1024)} MB needed)")

        dl_dir = os.path.join(root, ".downloads")
        archive = os.path.join(dl_dir, f"{gid}-{up['id']}-{re.sub(r'[^A-Za-z0-9._-]', '_', up['filename'])[-80:] or 'download'}")
        job["_t0"] = time.monotonic()
        self._progress(job, "downloading", 0, up["size"])
        if not os.path.isfile(archive):
            install.download(key, up, g.get("key", 0), archive, lambda d, t: self._progress(job, "downloading", d, t), cancel)
        if cancel.is_set():
            raise install.Cancelled()

        name = install.slug(g["title"], gid)
        final = prev["dir"] if prev and prev.get("dir") and install.inside(root, prev["dir"]) else os.path.join(root, name)
        staging = os.path.join(root, f".staging-{gid}")
        install.rmtree(staging)
        self._progress(job, "unpacking")
        try:
            info = install.unpack(archive, staging, up["filename"], cancel)
            shipped = install.file_list(staging)
            if not shipped:
                raise install.InstallError("The download was empty")
            receipts = os.path.join(self.runtime, "receipts")
            receipt_path = os.path.join(receipts, f"{gid}.json")
            if prev and os.path.isdir(final):
                self._progress(job, "merging")
                old_receipt = read_json(receipt_path, [])
                install.carry_over(final, staging, old_receipt or None)
                old = os.path.join(root, f".old-{gid}")
                install.rmtree(old)
                os.replace(final, old)
                os.replace(staging, final)
                install.rmtree(old)
            else:
                install.rmtree(final)
                os.replace(staging, final)
            write_json(receipt_path, shipped)
        except BaseException:
            install.rmtree(staging)
            raise
        finally:
            if not self.settings.data["keep_downloads"]:
                try:
                    os.unlink(archive)
                except OSError:
                    pass

        # Pick what Steam launches: keep the user's choice across updates if it still exists.
        self._progress(job, "finishing")
        prefer_kind = "linux" if "linux" in up["platforms"] and (
            self.settings.data["prefer"] != "windows" or "windows" not in up["platforms"]) else "windows"
        cands = install.scan(final, g["title"], up.get("targets") or [], prefer_kind)
        exe, kind, args = "", prefer_kind, ""
        if prev and prev.get("exe") and prev.get("dir"):
            rel = os.path.relpath(prev["exe"], prev["dir"]) if install.inside(prev["dir"], prev["exe"]) else ""
            if rel and os.path.isfile(os.path.join(final, rel)):
                exe, kind, args = os.path.join(final, rel), prev.get("kind", kind), prev.get("args", "")
        if not exe and cands:
            exe, kind, args = os.path.join(final, cands[0]["path"]), cands[0]["kind"], cands[0]["args"]
        if not exe:
            raise install.InstallError("Installed, but no game executable was found in it")
        if kind == "linux":
            install.make_executable(exe)
        rec = {
            "game_id": gid, "title": g["title"], "key": g.get("key", 0), "cover": g.get("still") or g.get("cover", ""),
            "url": g.get("url", ""), "upload_id": up["id"], "upload_name": up["name"], "fingerprint": api.fingerprint(up),
            "version": up.get("version", ""), "root": root, "dir": final, "exe": exe, "kind": kind, "args": args,
            "installer": info.get("installer", ""), "appid": (prev or {}).get("appid", 0),
            "min_price": int(g.get("min_price") or 0), "demo": bool(up.get("demo")),
            "installed_at": int(time.time()), "size": install.dir_size(final),
        }
        self.installed.put(gid, rec)
        self.update_info.pop(str(gid), None)
        return self._installed_view(rec)

    # ------------------------------------------------------------ installed games

    async def set_shortcut(self, game_id: int, appid: int):
        rec = self.installed.get(game_id)
        if not rec:
            return None
        rec["appid"] = int(appid or 0)
        self.installed.put(game_id, rec)
        return self._installed_view(rec)

    def _prefix_dir(self, appid: int) -> str:
        return os.path.join(steam_root(self.home), "steamapps", "compatdata", str(int(appid)))

    async def executables(self, game_id: int):
        rec = self.installed.get(game_id)
        if not rec:
            return []

        def run():
            out = [{**c, "path": os.path.join(rec["dir"], c["path"])} for c in install.scan(rec["dir"], rec["title"], [])]
            # A Windows installer that ran through Proton put the game inside its prefix.
            if rec.get("kind") == "windows" and rec.get("appid"):
                drive = os.path.join(self._prefix_dir(rec["appid"]), "pfx", "drive_c")
                for sub in ("Program Files", "Program Files (x86)", "Games", "users/steamuser/AppData/Local/Programs"):
                    d = os.path.join(drive, sub)
                    if os.path.isdir(d):
                        out += [{**c, "path": os.path.join(d, c["path"]), "score": c["score"] - 5}
                                for c in install.scan(d, rec["title"], []) if c["kind"] == "windows"]
            out = [c for c in out if not install.HELPERS.search(os.path.basename(c["path"]).lower()) or c["path"] == rec["exe"]]
            out.sort(key=lambda c: c["score"], reverse=True)
            return out[:40]
        return await asyncio.to_thread(run)

    async def set_exe(self, game_id: int, path: str):
        rec = self.installed.get(game_id)
        if not rec:
            return {"ok": False, "error": "Not installed"}
        path = os.path.realpath(path or "")
        allowed = [rec["dir"]] + ([self._prefix_dir(rec["appid"])] if rec.get("appid") else [])
        if not os.path.isfile(path) or not any(install.inside(a, path) for a in allowed):
            return {"ok": False, "error": "Pick a file inside the game's folder"}
        rec["exe"] = path
        rec["kind"] = "windows" if path.lower().endswith(".exe") else "linux"
        rec["args"] = ""
        if rec["kind"] == "linux":
            install.make_executable(path)
        if not path.endswith(".exe") or not install.windows_installer(path):
            rec["installer"] = ""
        self.installed.put(game_id, rec)
        return {"ok": True, "installed": self._installed_view(rec)}

    async def uninstall(self, game_id: int, delete_prefix: bool = False):
        rec = self.installed.get(game_id)
        if not rec:
            return {"ok": True, "appid": 0}
        if any(j["game_id"] == int(game_id) for j in self.jobs):
            return {"ok": False, "error": "Wait for its download to finish or cancel it first"}
        d = rec.get("dir", "")
        root = rec.get("root", "")

        def run():
            # Only ever delete a folder this plugin made: <root>/<name>-<game id>.
            if d and root and install.inside(root, d) and os.path.realpath(d) != os.path.realpath(root) \
                    and os.path.basename(d.rstrip("/")).endswith(f"-{int(game_id)}"):
                install.rmtree(d)
            if delete_prefix and rec.get("appid"):
                p = self._prefix_dir(rec["appid"])
                if os.path.isdir(p):
                    install.rmtree(p)
            for f in (os.path.join(self.runtime, "receipts", f"{int(game_id)}.json"),
                      os.path.join(self.runtime, "icons", f"{int(game_id)}.png")):
                try:
                    os.unlink(f)
                except OSError:
                    pass
        try:
            await asyncio.to_thread(run)
        except Exception as e:
            return _err(e)
        self.installed.drop(game_id)
        self.update_info.pop(str(int(game_id)), None)
        return {"ok": True, "appid": int(rec.get("appid") or 0)}

    async def check_updates(self):
        key = self._key()
        recs = list(self.installed.games.values())
        if not key or not recs:
            return {"ok": True, "updates": 0, "checked": 0, "installed": {}}

        def one(rec):
            try:
                owned = bool(self._owned(rec["game_id"])) or bool(rec.get("key"))
                ups = [u for u in api.uploads(key, rec["game_id"], rec.get("key", 0))
                       if self._allowed({"min_price": rec.get("min_price", 0)}, owned, u)]
            except api.ApiError as e:
                return rec["game_id"], {"error": str(e)}
            same = next((u for u in ups if u["id"] == rec.get("upload_id") and api.installable(u)), None)
            if same:
                return rec["game_id"], {"available": api.fingerprint(same) != rec.get("fingerprint"), "upload": same}
            alt = api.pick_upload([u for u in ups if rec.get("kind") in u["platforms"]] or ups, rec.get("kind") or "linux")
            return rec["game_id"], {"available": bool(alt), "upload": alt}

        def run():
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                return list(ex.map(one, recs))
        results = await asyncio.to_thread(run)
        n = 0
        for gid, info in results:
            if "error" in info:
                continue
            if info.get("upload"):
                info["upload"].pop("targets", None)
            self.update_info[str(gid)] = info
            n += 1 if info.get("available") else 0
        self.last_update_check = time.time()
        return {"ok": True, "updates": n, "checked": len(recs),
                "installed": {k: self._installed_view(v) for k, v in self.installed.games.items()}}

    async def installed_list(self):
        return {k: self._installed_view(v) for k, v in self.installed.games.items()}

    # ------------------------------------------------------------ lifecycle

    async def _main(self):
        self.loop = asyncio.get_running_loop()
        # Leftovers from an interrupted install (power loss, Decky restart) are removed once.
        def tidy():
            root = self._root()
            try:
                for n in os.listdir(root):
                    if n.startswith((".staging-", ".old-")):
                        install.rmtree(os.path.join(root, n))
                dl = os.path.join(root, ".downloads")
                for n in os.listdir(dl) if os.path.isdir(dl) else []:
                    if n.endswith(".part"):
                        os.unlink(os.path.join(dl, n))
            except OSError:
                pass
        await asyncio.to_thread(tidy)
        decky.logger.info("Itch Library ready (idle until opened)")

    async def _unload(self):
        for j in self.jobs:
            j["cancel"].set()
        self.handoff.stop()
