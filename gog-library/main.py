"""GOG Library - Decky backend.

Runs as the normal user (no "root" flag) and does nothing in the background:
- signs in to GOG with GOG's own sign-in page (from the phone) and keeps the tokens here;
- lists owned games and the GOG store catalog, only when the library page asks;
- installs one game at a time when asked: native Linux installers, or Windows builds from GOG
  Galaxy's content system (file by file, so updates only fetch what changed), with the classic
  Windows installer as a fallback; progress is reported as events;
- keeps a small record of installed games so the frontend can add/update Steam shortcuts.
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

from goglib import api, galaxy, install  # noqa: E402
from goglib.handoff import Handoff  # noqa: E402
from goglib.store import Installed, Settings, read_json, write_json  # noqa: E402

LIBRARY_TTL = 30 * 60          # owned-games list is refreshed on open after this
UPDATE_TTL = 6 * 3600          # automatic update check on open at most this often
ART_KINDS = ("capsule", "wide", "hero", "logo", "icon")
LANGUAGES = ("en-US", "de-DE", "fr-FR", "es-ES", "it-IT", "pl-PL", "pt-BR", "ru-RU", "zh-Hans", "ja-JP", "ko-KR")


def _err(e: BaseException) -> dict:
    if not isinstance(e, (api.ApiError, install.InstallError, galaxy.DownloadError)):
        decky.logger.error(f"unexpected error: {e!r}")
    return {"ok": False, "error": str(e) or e.__class__.__name__, "status": getattr(e, "status", 0)}


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
        self.auth = api.Auth(lambda: self.settings.data["auth"], self._save_auth)
        self.loop = None
        self.jobs: list = []          # queue, first = running
        self.job_lock = threading.Lock()
        self.worker = None
        self.handoff = Handoff(self._handoff_code)
        self.update_info: dict = {}   # game id -> {"available": bool, "version": str}
        self.last_update_check = 0.0
        self.seen: dict = {}          # store games opened from Browse (not owned), by id

    # ------------------------------------------------------------ plumbing

    def _emit(self, event: str, payload) -> None:
        """Thread-safe decky.emit (events reach the frontend only while it listens)."""
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(decky.emit(event, payload), self.loop)
            except RuntimeError:
                pass

    def _save_auth(self, t: dict) -> None:
        self.settings.data["auth"] = t
        self.settings.save()

    def _token(self) -> str:
        return self.auth.token()

    def _root(self) -> str:
        return self.settings.data["root"] or os.path.join(self.home, "Games", "gog")

    def _public(self) -> dict:
        d = self.settings.public()
        d["root"] = self._root()
        d["home"] = self.home
        d["languages"] = list(LANGUAGES)
        return d

    def _sign_in(self, pasted: str) -> tuple:
        code = api.extract_code(pasted)
        if not code:
            return False, "That doesn't look like the GOG sign-in address. Copy the whole address of the page GOG showed after signing in."
        try:
            t = api.exchange_code(code)
            self._save_auth(t)
            user = api.user_data(t["access_token"])
        except api.ApiError as e:
            return False, str(e)
        self.settings.data["user"] = {"id": user["id"] or t.get("user_id", ""), "username": user["username"]}
        self.settings.save()
        self._drop_library_cache()
        decky.logger.info(f"signed in to GOG as {user['username']}")
        return True, f"Signed in as {user['username'] or 'your GOG account'}."

    def _handoff_code(self, pasted: str) -> tuple:
        ok, msg = self._sign_in(pasted)
        if ok:
            self._emit("gog_signed_in", self._public())
        return ok, msg

    def _library_path(self) -> str:
        return os.path.join(self.runtime, "library.json")

    def _drop_library_cache(self) -> None:
        try:
            os.unlink(self._library_path())
        except OSError:
            pass

    def _receipt_path(self, gid) -> str:
        return os.path.join(self.runtime, "receipts", f"{int(gid)}.json")

    def _installed_view(self, rec: dict) -> dict:
        gid = str(rec.get("game_id"))
        u = self.update_info.get(gid) or {}
        return {**rec, "present": os.path.isdir(rec.get("dir", "")), "update": bool(u.get("available")),
                "update_name": u.get("version", "")}

    def _job_view(self, j: dict) -> dict:
        return {k: j[k] for k in ("game_id", "title", "action", "phase", "done", "total", "speed", "error") if k in j}

    # ------------------------------------------------------------ settings / sign-in

    async def settings_get(self):
        return self._public()

    async def sign_in(self, pasted: str):
        ok, msg = await asyncio.to_thread(self._sign_in, pasted)
        return {"ok": ok, "message": msg, "settings": self._public()}

    async def login_url(self):
        return api.LOGIN_URL

    async def sign_out(self):
        self.settings.data["auth"] = {}
        self.settings.data["user"] = {}
        self.settings.save()
        self._drop_library_cache()
        self.update_info.clear()
        return self._public()

    async def handoff_start(self):
        return await asyncio.to_thread(self.handoff.start)

    async def handoff_status(self):
        return {**self.handoff.status(), "signedIn": bool(self._public().get("signedIn"))}

    async def handoff_stop(self):
        await asyncio.to_thread(self.handoff.stop)
        return True

    async def set_options(self, opts: dict):
        s = self.settings.data
        if opts.get("prefer") in ("linux", "windows"):
            s["prefer"] = opts["prefer"]
        if isinstance(opts.get("tool"), str):
            s["tool"] = opts["tool"][:120]
        if opts.get("language") in LANGUAGES:
            s["language"] = opts["language"]
        if opts.get("art") in ("gog", "nightgrid"):
            s["art"] = opts["art"]
        if "keep_downloads" in opts:
            s["keep_downloads"] = bool(opts["keep_downloads"])
        if isinstance(opts.get("root"), str):
            # /home is a symlink to /var/home on Bazzite, so compare resolved paths.
            want = os.path.realpath(opts["root"]) if opts["root"] else ""
            match = next((r["path"] for r in self._roots() if os.path.realpath(r["path"]) == want), None)
            if want and not match:
                return {"ok": False, "error": "That folder isn't one of the offered locations"}
            internal = os.path.realpath(os.path.join(self.home, "Games", "gog"))
            s["root"] = "" if not want or want == internal else match
        self.settings.save()
        return {"ok": True, "settings": self._public()}

    def _roots(self) -> list:
        """Internal storage plus every writable removable drive (SD card, USB)."""
        out = [{"path": os.path.join(self.home, "Games", "gog"), "label": "Internal"}]
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
                out.append({"path": os.path.join(m, "Games", "gog"), "label": f"Drive · {n}"})
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
        uid = self.settings.data["user"].get("id")
        fresh = cache.get("user") == uid and time.time() - float(cache.get("at", 0)) < LIBRARY_TTL
        if refresh or not fresh or not isinstance(cache.get("games"), list):
            games = api.library(token)
            try:
                owned = api.owned_ids(token)
            except api.ApiError:
                owned = [g["id"] for g in games]
            cache = {"at": time.time(), "user": uid, "games": games, "owned": owned}
            write_json(self._library_path(), cache)
        return {"games": [g for g in cache["games"] if not g.get("hidden")], "at": cache["at"]}

    async def library(self, refresh: bool = False):
        try:
            lib = await asyncio.to_thread(self._library, bool(refresh))
        except Exception as e:
            return _err(e)
        inst = {k: self._installed_view(v) for k, v in self.installed.games.items()}
        due = time.time() - self.last_update_check > UPDATE_TTL and bool(inst)
        return {"ok": True, **lib, "installed": inst, "jobs": [self._job_view(j) for j in self.jobs],
                "updatesDue": due}

    def _cache(self) -> dict:
        return read_json(self._library_path(), {})

    def _owned(self, game_id: int) -> dict | None:
        for g in self._cache().get("games") or []:
            if g.get("id") == int(game_id):
                return g
        return None

    def _owned_ids(self) -> set:
        c = self._cache()
        return set(int(x) for x in c.get("owned") or []) | {int(g["id"]) for g in c.get("games") or []}

    def _find_game(self, game_id: int) -> dict | None:
        g = self._owned(game_id)
        if g:
            return g
        rec = self.installed.get(game_id)
        if rec:
            return {"id": int(game_id), "title": rec.get("title", ""), "cover": rec.get("cover", ""), "image": rec.get("cover", ""),
                    "url": rec.get("url", ""), "platforms": [rec.get("kind", "")], "category": ""}
        return self.seen.get(int(game_id))

    @staticmethod
    def _options(prod: dict, lang: str) -> list:
        out = []
        for os_ in ("linux", "windows"):
            i = api.pick_installer(prod.get("installers") or [], os_, lang)
            if i:
                out.append({"kind": os_, "version": i["version"], "size": i["size"], "language": i["language"]})
            elif os_ == "windows" and "windows" in prod.get("platforms", []):
                out.append({"kind": "windows", "version": "", "size": 0, "language": ""})
        return out

    async def game(self, game_id: int, hint: dict | None = None):
        gid = int(game_id)
        owned_g = self._owned(gid)
        g = owned_g or self._find_game(gid) or {}
        if not owned_g and isinstance(hint, dict) and hint.get("id") == gid:
            g = {**hint, **g}
            self.seen[gid] = g
        try:
            token = self._token() if self.auth.signed_in() else ""
        except api.ApiError:
            token = ""
        owned = bool(owned_g) or gid in self._owned_ids()
        rec = self.installed.get(gid)
        try:
            prod = await asyncio.to_thread(api.product, gid, token if owned else "")
        except Exception as e:
            if not g:
                return _err(e)
            r = _err(e)
            r.update({"game": g, "owned": owned, "installed": self._installed_view(rec) if rec else None, "options": []})
            return r
        g = {**g, "id": gid, "title": g.get("title") or prod["title"], "short": prod["short"],
             "platforms": prod["platforms"] or g.get("platforms", []), "background": prod["background"],
             "url": g.get("url") or prod["url"], "preorder": prod["preorder"]}
        if not g.get("cover"):
            g["cover"] = prod["background"]
        if not owned_g:
            self.seen[gid] = g
        dlcs = [d for d in prod["dlcs"] if d["id"] in self._owned_ids()]
        return {"ok": True, "game": g, "owned": owned, "installed": self._installed_view(rec) if rec else None,
                "options": self._options(prod, self.settings.data["language"]) if owned else [],
                "dlcs": [{"id": d["id"], "title": d["title"]} for d in dlcs]}

    # ------------------------------------------------------------ store

    async def browse(self, opts: dict):
        o = opts if isinstance(opts, dict) else {}
        s = self.settings.data
        try:
            res = await asyncio.to_thread(
                api.catalog, str(o.get("sort", "")), str(o.get("price", "")), str(o.get("genre", "")),
                str(o.get("controller", "controller")), str(o.get("platform", "")), str(o.get("query", ""))[:100],
                int(o.get("page", 1) or 1), s["country"], s["currency"])
            return {"ok": True, **res}
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------ artwork

    def _art_urls(self, gid: int) -> dict:
        path = os.path.join(self.runtime, "art", f"{gid}.json")
        cached = read_json(path, {})
        if cached.get("at", 0) > time.time() - 7 * 86400:
            return cached
        urls = api.gamesdb_art(gid)
        g = self._find_game(gid) or {}
        urls["cover"] = g.get("vertical") or g.get("image") or g.get("cover") or ""
        urls["at"] = time.time()
        write_json(path, urls)
        return urls

    async def art(self, game_id: int, kind: str):
        """One artwork image as base64 (Steam takes them one at a time). kind: capsule, wide, hero,
        logo, icon, or cover (the picture the Nightgrid look draws from)."""
        if kind not in ART_KINDS + ("cover",):
            return {"ok": False, "error": "Unknown artwork"}
        try:
            urls = await asyncio.to_thread(self._art_urls, int(game_id))
            url = urls.get(kind) or ""
            if not url:
                return {"ok": False, "error": "GOG has no such artwork for this game"}
            data, ext = await asyncio.to_thread(api.image, url)
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

    async def install(self, game_id: int, kind: str = ""):
        g = self._find_game(game_id)
        if not g:
            return {"ok": False, "error": "Open the game first so its details are known"}
        with self.job_lock:
            if any(j["game_id"] == int(game_id) for j in self.jobs):
                return {"ok": True, "queued": True, "jobs": [self._job_view(j) for j in self.jobs]}
            action = "update" if self.installed.get(game_id) else "install"
            self.jobs.append({"game_id": int(game_id), "title": g["title"], "game": g,
                              "kind": kind if kind in ("linux", "windows") else "",
                              "action": action, "phase": "queued", "done": 0, "total": 0, "speed": 0, "error": "",
                              "cancel": threading.Event()})
        self._emit("gog_job", [self._job_view(j) for j in self.jobs])
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
        self._emit("gog_job", jobs)
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
            except (install.Cancelled, galaxy.Cancelled):
                job["phase"] = "cancelled"
            except Exception as e:
                job["phase"] = "error"
                job["error"] = str(e) or e.__class__.__name__
                if not isinstance(e, (api.ApiError, install.InstallError, galaxy.DownloadError)):
                    decky.logger.exception("install failed")
            with self.job_lock:
                if job in self.jobs:
                    self.jobs.remove(job)
            await decky.emit("gog_job_done", {**self._job_view(job), "result": result})
            await decky.emit("gog_job", [self._job_view(j) for j in self.jobs])

    def _progress(self, job: dict, phase: str, done: int = 0, total: int = 0):
        now = time.monotonic()
        if phase == "downloading":
            if not job.get("_t0") or job.get("phase") != "downloading":
                job["_t0"], job["_d0"] = now, done
            dt = now - job["_t0"]
            job["speed"] = int((done - job["_d0"]) / dt) if dt > 0.5 else 0
        job.update(phase=phase, done=max(0, done), total=total)
        self._emit("gog_job", [self._job_view(j) for j in self.jobs])

    def _method(self, job: dict, prod: dict, prev: dict | None, token: str) -> tuple:
        """('linux', installer) | ('galaxy', build) | ('installer', installer) for this install."""
        lang = self.settings.data["language"]
        lin = api.pick_installer(prod["installers"], "linux", lang)
        win = api.pick_installer(prod["installers"], "windows", lang)
        want = job["kind"] or (prev or {}).get("kind") or self.settings.data["prefer"]
        if lin and (want == "linux" or not (win or "windows" in prod["platforms"])):
            return "linux", lin
        build = api.pick_build(api.builds(job["game_id"], "windows", token))
        if build:
            return "galaxy", build
        if win:
            return "installer", win
        if lin:
            return "linux", lin
        raise install.InstallError("GOG has no Linux or Windows download of this game for your account")

    def _run_job(self, job: dict) -> dict:
        token = self._token()
        g = job["game"]
        gid = job["game_id"]
        prev = self.installed.get(gid)
        self._progress(job, "preparing")
        prod = api.product(gid, token)
        method, src = self._method(job, prod, prev, token)
        root = os.path.realpath(prev["root"]) if prev and prev.get("root") else self._root()
        os.makedirs(root, exist_ok=True)
        final = prev["dir"] if prev and prev.get("dir") and install.inside(root, prev["dir"]) else \
            os.path.join(root, install.slug(g["title"], gid))
        rec_extra: dict = {}
        if method == "galaxy":
            rec_extra = self._install_galaxy(job, src, final, prev, token)
            kind = "windows"
        else:
            rec_extra = self._install_installer(job, method, src, root, final, prev, token)
            kind = "linux" if method == "linux" else "windows"

        # What Steam launches: keep the user's choice across updates if it still exists.
        self._progress(job, "finishing")
        exe, args, workdir = "", "", ""
        if prev and prev.get("exe") and prev.get("dir") and prev.get("picked"):
            rel = os.path.relpath(prev["exe"], prev["dir"]) if install.inside(prev["dir"], prev["exe"]) else ""
            if rel and os.path.isfile(os.path.join(final, rel)):
                exe, args, workdir = os.path.join(final, rel), prev.get("args", ""), os.path.dirname(os.path.join(final, rel))
        if not exe and rec_extra.get("installer"):
            exe = rec_extra["installer"]
        if not exe and kind == "linux" and os.path.isfile(os.path.join(final, "start.sh")):
            exe = os.path.join(final, "start.sh")
        if not exe and kind == "windows":
            t = install.play_task(final, gid)
            if t:
                exe, args, workdir = t["exe"], t["args"], t["workdir"]
        if not exe:
            cands = install.scan(final, g["title"], [], kind)
            if cands:
                exe, args = os.path.join(final, cands[0]["path"]), cands[0]["args"]
                kind = cands[0]["kind"]
        if not exe:
            raise install.InstallError("Installed, but no game executable was found in it")
        if kind == "linux":
            install.make_executable(exe)
        rec = {
            "game_id": gid, "title": g["title"], "cover": g.get("cover", ""), "url": g.get("url", ""),
            "method": method, "kind": kind, "version": rec_extra.get("version", ""), "build_id": rec_extra.get("build_id", ""),
            "fingerprint": rec_extra.get("fingerprint", ""), "root": root, "dir": final, "exe": exe, "args": args,
            "workdir": workdir or os.path.dirname(exe), "installer": bool(rec_extra.get("installer")),
            "picked": bool(prev and prev.get("picked") and exe == os.path.join(final, os.path.relpath(prev["exe"], prev["dir"]))),
            "appid": (prev or {}).get("appid", 0), "installed_at": int(time.time()), "size": install.dir_size(final),
        }
        self.installed.put(gid, rec)
        self.update_info.pop(str(gid), None)
        return self._installed_view(rec)

    def _install_galaxy(self, job: dict, build: dict, final: str, prev: dict | None, token: str) -> dict:
        gid = job["game_id"]
        p = galaxy.plan(gid, build, token, self.settings.data["language"], self._owned_ids())
        if not p["files"]:
            raise install.InstallError("GOG's build of this game has no files for your language")
        fresh = not (prev and prev.get("method") == "galaxy" and os.path.isdir(final))
        old = None if fresh else (read_json(self._receipt_path(gid), {}) or None)
        self._progress(job, "downloading", 0, 0)
        ex = galaxy.Executor(gid, p, final, self._token, lambda d, t: self._progress(job, "downloading", d, t), job["cancel"])
        existed = os.path.isdir(final)
        try:
            receipt = ex.run(old, install.free_bytes)
        except (galaxy.Cancelled, install.Cancelled):
            if fresh and not existed and not prev:
                install.rmtree(final)
            raise
        write_json(self._receipt_path(gid), receipt)
        return {"version": p["version"], "build_id": p["build_id"], "fingerprint": p["build_id"]}

    def _install_installer(self, job: dict, method: str, inst: dict, root: str, final: str, prev: dict | None, token: str) -> dict:
        gid = job["game_id"]
        cancel = job["cancel"]
        total = sum(f["size"] for f in inst["files"]) or inst["size"]
        need = int(total * 2.2) + 256 * 1024 * 1024
        if total and install.free_bytes(root) < need:
            raise install.InstallError(f"Not enough free space in {root} (about {need // (1024 * 1024)} MB needed)")
        dl_dir = os.path.join(root, ".downloads")
        paths, names = [], []
        self._progress(job, "downloading", 0, total)
        base = 0
        for i, f in enumerate(inst["files"]):
            if cancel.is_set():
                raise install.Cancelled()
            url = api.downlink(f["downlink"], self._token())
            name = os.path.basename(url.split("?")[0]) or f"part{i}"
            name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-100:]
            dest = os.path.join(dl_dir, f"{gid}-{inst['version'] or 'v'}-{name}".replace("/", "_"))
            if not os.path.isfile(dest):
                install.download(url, f["size"], dest, lambda d: self._progress(job, "downloading", d, total), cancel, base)
            base += f["size"] or os.path.getsize(dest)
            paths.append(dest)
            names.append(name)
        if cancel.is_set():
            raise install.Cancelled()

        staging = os.path.join(root, f".staging-{gid}")
        install.rmtree(staging)
        self._progress(job, "unpacking")
        installer_exe = ""
        try:
            os.makedirs(staging, exist_ok=True)
            if method == "linux":
                install.extract_linux(paths[0], staging, cancel)
            elif not install.extract_windows(paths[0], staging, cancel):
                # No innoextract: keep the installer; Play runs it once through Proton.
                for pth, name in zip(paths, names):
                    install.shutil.copyfile(pth, os.path.join(staging, name))
                installer_exe = names[0]
            shipped = install.file_list(staging)
            if not shipped:
                raise install.InstallError("The download was empty")
            if prev and os.path.isdir(final):
                self._progress(job, "merging")
                old_receipt = read_json(self._receipt_path(gid), [])
                install.carry_over(final, staging, old_receipt if isinstance(old_receipt, list) and old_receipt else None)
                old = os.path.join(root, f".old-{gid}")
                install.rmtree(old)
                os.replace(final, old)
                os.replace(staging, final)
                install.rmtree(old)
            else:
                install.rmtree(final)
                os.replace(staging, final)
            write_json(self._receipt_path(gid), shipped)
        except BaseException:
            install.rmtree(staging)
            raise
        finally:
            if not self.settings.data["keep_downloads"]:
                for pth in paths:
                    try:
                        os.unlink(pth)
                    except OSError:
                        pass
        out = {"version": inst["version"], "fingerprint": f"{inst['id']}:{inst['version']}:{inst['size']}"}
        if installer_exe:
            out["installer"] = os.path.join(final, installer_exe)
        return out

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
            start = os.path.join(rec["dir"], "start.sh")
            if os.path.isfile(start) and not any(c["path"] == start for c in out):
                out.append({"path": start, "kind": "linux", "score": 500, "size": 0, "args": ""})
            # A Windows installer that ran through Proton put the game inside its prefix.
            if rec.get("kind") == "windows" and rec.get("appid"):
                drive = os.path.join(self._prefix_dir(rec["appid"]), "pfx", "drive_c")
                for sub in ("GOG Games", "Program Files", "Program Files (x86)", "Games"):
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
        rec["workdir"] = os.path.dirname(path)
        rec["picked"] = True
        if rec["kind"] == "linux":
            install.make_executable(path)
        if not path.lower().endswith(".exe") or not install.windows_installer(path):
            rec["installer"] = False
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
            for f in (self._receipt_path(game_id), os.path.join(self.runtime, "icons", f"{int(game_id)}.png"),
                      os.path.join(self.runtime, "art", f"{int(game_id)}.json")):
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

    def _check_one(self, rec: dict, token: str) -> tuple:
        gid = rec["game_id"]
        try:
            if rec.get("method") == "galaxy":
                b = api.pick_build(api.builds(gid, "windows", token))
                if not b:
                    return gid, {"available": False}
                return gid, {"available": str(b.get("build_id") or "") != rec.get("build_id"), "version": str(b.get("version_name") or "")}
            prod = api.product(gid, token)
            os_ = "linux" if rec.get("method") == "linux" else "windows"
            i = api.pick_installer(prod["installers"], os_, self.settings.data["language"])
            if not i:
                return gid, {"available": False}
            fp = f"{i['id']}:{i['version']}:{i['size']}"
            return gid, {"available": fp != rec.get("fingerprint"), "version": i["version"]}
        except api.ApiError as e:
            return gid, {"error": str(e)}

    async def check_updates(self):
        recs = list(self.installed.games.values())
        if not recs or not self.auth.signed_in():
            return {"ok": True, "updates": 0, "checked": 0, "installed": {}}
        try:
            token = await asyncio.to_thread(self._token)
        except Exception as e:
            return _err(e)

        def run():
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                return list(ex.map(lambda r: self._check_one(r, token), recs))
        results = await asyncio.to_thread(run)
        n = 0
        for gid, info in results:
            if "error" in info:
                continue
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
        decky.logger.info("GOG Library ready (idle until opened)")

    async def _unload(self):
        for j in self.jobs:
            j["cancel"].set()
        self.handoff.stop()
