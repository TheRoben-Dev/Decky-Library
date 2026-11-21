"""Legendary as a separate program.

Legendary (GPL-3.0-or-later, https://github.com/derrod/legendary) does everything that talks to
Epic's launcher services: sign-in, the owned-games list, downloads, updates and launch tokens. It
is bundled unmodified in runtime/site and run with the system Python (`python3 -I lgd.py ...`)
as its own process, never imported into this plugin. Its data lives in a folder of our own
(LEGENDARY_CONFIG_PATH), so it never touches a ~/.config/legendary the user may have.

Nothing here runs unless the user asked for it (open the library, install, uninstall...).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time

PYTHONS = ("/usr/bin/python3", "/usr/local/bin/python3", "/bin/python3") + tuple(
    f"/usr/bin/python3.{m}" for m in range(20, 9, -1))

LOG_LINE = re.compile(r"^\[[\w.]+\] (ERROR|CRITICAL|FATAL): (.*)$")
RE_PROGRESS = re.compile(r"= Progress: ([\d.]+)% \((\d+)/(\d+)\)")
RE_DOWNLOADED = re.compile(r"- Downloaded: ([\d.]+) MiB")
RE_SPEED = re.compile(r"\+ Download\s+- ([\d.]+) MiB/s")
RE_DL_SIZE = re.compile(r"Download size: ([\d.]+) MiB")
RE_INSTALL_SIZE = re.compile(r"Install size: ([\d.]+) MiB")
RE_PATH = re.compile(r"Install path: (.+)$")
MIB = 1024 * 1024


class LegendaryError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


class Cancelled(Exception):
    pass


def clean_env() -> dict:
    """Decky's bundled Python sets LD_LIBRARY_PATH; the system Python must not inherit it."""
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    return env


def find_python() -> str:
    """The system's Python 3.11+ (Bazzite and SteamOS ship one)."""
    for p in PYTHONS:
        if not os.access(p, os.X_OK):
            continue
        try:
            r = subprocess.run([p, "-I", "-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])"],
                               env=clean_env(), capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and int(r.stdout.strip() or 0) >= 311:
                return p
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return ""


def last_error(text: str) -> str:
    """The most useful line of Legendary's log output for a person to read."""
    err = ""
    tail = ""
    for line in (text or "").splitlines():
        line = line.rstrip()
        m = LOG_LINE.match(line)
        if m:
            err = m.group(2).strip()
        elif line and not line.startswith((" ", "\t", "Traceback")):
            tail = line
    if err:
        return err
    if "No saved credentials" in tail:
        return "Not signed in"
    return tail[-300:]


def _read(path: str, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


class Legendary:
    def __init__(self, runtime: str, config: str, cache: str):
        self.runtime = runtime      # folder with lgd.py, launch.sh and site/
        self.config = config        # Legendary's own data (sign-in, metadata, installed games)
        self.cache = cache
        self.python = ""

    # ------------------------------------------------------------ process plumbing

    def ready(self) -> str:
        """'' when Legendary can run, otherwise a reason a person understands."""
        if not os.path.isfile(os.path.join(self.runtime, "lgd.py")):
            return "The plugin's Legendary runtime is missing. Reinstall Epic Library."
        if not self.python:
            self.python = find_python()
        if not self.python:
            return "No Python 3.11 or newer found at /usr/bin/python3. Epic Library needs the system's Python."
        return ""

    def _env(self) -> dict:
        env = clean_env()
        env["LEGENDARY_CONFIG_PATH"] = self.config
        env["PYTHONPYCACHEPREFIX"] = os.path.join(self.cache, "pycache")
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _cmd(self, args: list) -> list:
        why = self.ready()
        if why:
            raise LegendaryError(why)
        return [self.python, "-I", os.path.join(self.runtime, "lgd.py")] + [str(a) for a in args]

    def run(self, args: list, timeout: int = 180, env: dict | None = None) -> str:
        """Runs Legendary and returns stdout. Raises LegendaryError with Legendary's own message."""
        e = self._env()
        if env:
            e.update(env)
        try:
            r = subprocess.run(self._cmd(args), env=e, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise LegendaryError("Epic didn't answer in time. Check your connection and try again.")
        except OSError as ex:
            raise LegendaryError(f"Couldn't start Legendary ({ex})")
        if r.returncode != 0:
            msg = last_error(r.stderr) or f"Legendary failed (exit {r.returncode})"
            raise LegendaryError(msg, 401 if msg == "Not signed in" or "Login failed" in msg else 0)
        return r.stdout

    def run_json(self, args: list, timeout: int = 180):
        out = self.run(args, timeout)
        try:
            return json.loads(out)
        except ValueError:
            raise LegendaryError("Legendary returned something unexpected")

    # ------------------------------------------------------------ account

    def user(self) -> dict:
        u = _read(os.path.join(self.config, "user.json"), {})
        if not u.get("account_id"):
            return {}
        return {"id": u.get("account_id", ""), "name": u.get("displayName", "")}

    def auth(self, code: str) -> dict:
        self.run(["auth", "--code", code, "--disable-webview"], timeout=60)
        u = self.user()
        if not u:
            raise LegendaryError("Epic didn't accept that code. Codes work once and only for a few minutes; get a new one.", 401)
        return u

    def sign_out(self) -> None:
        try:
            self.run(["auth", "--delete"], timeout=30)
        except LegendaryError:
            pass
        try:
            os.unlink(os.path.join(self.config, "user.json"))
        except OSError:
            pass

    # ------------------------------------------------------------ library

    def owned(self) -> list:
        """Every game the account owns (raw Legendary JSON, trimmed by library.py). Legendary always
        asks Epic for the current entitlements and only fetches metadata for games it hasn't seen,
        so this is quick after the first run."""
        data = self.run_json(["list", "--json", "--third-party"], timeout=600)
        return data if isinstance(data, list) else []

    def installed(self) -> dict:
        """app_name -> Legendary's install record (read from its file, no process)."""
        return _read(os.path.join(self.config, "installed.json"), {})

    def latest_versions(self) -> dict:
        """app_name -> newest Windows build version Legendary knows about (from its asset cache)."""
        assets = _read(os.path.join(self.config, "assets.json"), {})
        return {a.get("app_name"): a.get("build_version", "") for a in assets.get("Windows", []) if isinstance(a, dict)}

    def check_updates(self) -> dict:
        """Refreshes the asset list from Epic, then compares it with what's installed."""
        self.run(["list-installed", "--check-updates", "--json"], timeout=180)
        return self.latest_versions()

    def info(self, app: str) -> dict:
        d = self.run_json(["info", app, "--json"], timeout=120)
        m = (d or {}).get("manifest") or {}
        return {"disk": int(m.get("disk_size") or 0), "download": int(m.get("download_size") or 0)}

    def resume_file(self, app: str) -> str:
        p = os.path.join(self.config, "tmp", f"{app}.resume")
        return p if os.path.isfile(p) else ""

    # ------------------------------------------------------------ install / uninstall

    def install(self, app: str, base_path: str, dlcs: bool, progress, cancel: threading.Event,
                repair: bool = False) -> dict:
        """Installs, updates (same command once installed) or repairs a game. progress(phase, done,
        total, speed, path) is called as Legendary reports; returns {"path", "noop"}."""
        args = ["-y", "install", app, "--platform", "Windows", "--skip-sdl",
                "--with-dlcs" if dlcs else "--skip-dlcs"]
        if base_path:
            args += ["--base-path", base_path]
        if repair:
            args.append("--repair")
        proc = subprocess.Popen(self._cmd(args), env=self._env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                bufsize=1, start_new_session=True)
        state = {"total": 0, "done": 0, "speed": 0, "path": "", "noop": False, "err": "", "tail": []}

        def stopper():
            while not cancel.wait(1):
                if proc.poll() is not None:
                    return
            if proc.poll() is None:
                # SIGINT lets Legendary save its resume file; the next install continues from there.
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                    proc.wait(timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except OSError:
                        pass
        threading.Thread(target=stopper, daemon=True).start()

        last = 0.0
        try:
            for line in proc.stderr:
                line = line.rstrip("\n")
                state["tail"] = (state["tail"] + [line])[-40:]
                m = LOG_LINE.match(line)
                if m:
                    state["err"] = m.group(2).strip()
                if (m := RE_PATH.search(line)):
                    state["path"] = m.group(1).strip()
                    progress("preparing", 0, 0, 0, state["path"])
                elif (m := RE_DL_SIZE.search(line)):
                    state["total"] = int(float(m.group(1)) * MIB)
                elif "Download size is 0" in line:
                    state["noop"] = True
                elif (m := RE_PROGRESS.search(line)):
                    pct = float(m.group(1)) / 100
                    state["done"] = int(state["total"] * pct) if state["total"] else 0
                    phase = "downloading" if pct < 1 else "finishing"
                    now = time.monotonic()
                    if now - last > 0.5 or pct >= 1:
                        last = now
                        progress(phase, state["done"], state["total"], state["speed"], state["path"])
                elif (m := RE_SPEED.search(line)):
                    state["speed"] = int(float(m.group(1)) * MIB)
                elif "Finished installation" in line or "Finished repair" in line:
                    progress("finishing", state["total"], state["total"], 0, state["path"])
        finally:
            rc = proc.wait()
            proc.stderr.close()
        if cancel.is_set():
            raise Cancelled()
        if rc != 0:
            msg = state["err"] or last_error("\n".join(state["tail"])) or f"Legendary failed (exit {rc})"
            raise LegendaryError(msg)
        return {"path": state["path"], "noop": state["noop"], "error": state["err"]}

    def uninstall(self, app: str) -> None:
        self.run(["-y", "uninstall", app, "--skip-uninstaller"], timeout=600)

    def discard(self, app: str, partial_dir: str, roots: list) -> None:
        """Drops a cancelled download: its resume file and, if it's inside an install folder we
        offered, the half-written game folder."""
        for p in (os.path.join(self.config, "tmp", f"{app}.resume"),):
            try:
                os.unlink(p)
            except OSError:
                pass
        if partial_dir and app not in self.installed():
            real = os.path.realpath(partial_dir)
            for r in roots:
                rr = os.path.realpath(r)
                if real != rr and real.startswith(rr + os.sep) and os.path.isdir(real):
                    shutil.rmtree(real, ignore_errors=True)
                    break

    # ------------------------------------------------------------ cloud saves

    def sync_saves(self, app: str, compatdata: str, direction: str) -> str:
        """direction 'download' or 'upload'. Uses the Steam shortcut's Proton prefix."""
        args = ["-y", "sync-saves", app, "--accept-path"]
        args.append("--force-download" if direction == "download" else "--force-upload")
        args.append("--skip-upload" if direction == "download" else "--skip-download")
        env = {"STEAM_COMPAT_DATA_PATH": compatdata}
        e = self._env()
        e.update(env)
        try:
            r = subprocess.run(self._cmd(args), env=e, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise LegendaryError("Epic didn't answer in time.")
        log = r.stderr or ""
        if r.returncode != 0 and "KeyError" in log and direction == "download":
            return "There's no cloud save on Epic for this game yet."
        if r.returncode != 0:
            raise LegendaryError(last_error(log) or "Cloud save sync failed")
        if "No cloud or local savegame found" in log:
            return "No cloud or local save found."
        if "Downloading remote savegame" in log:
            return "Cloud save downloaded."
        if "Uploading local savegame" in log:
            return "Save uploaded to Epic."
        if "unprocessed variables" in log or "skipping due to --yes" in log:
            raise LegendaryError("Couldn't work out where this game keeps its saves.")
        if "does not support cloud saves" in log:
            return "This game doesn't use Epic cloud saves."
        return last_error(log) or "Saves are already in sync."
