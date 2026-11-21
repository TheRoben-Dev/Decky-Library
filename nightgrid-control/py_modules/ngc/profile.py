"""Nightgrid profiles: the hosts this plugin shows, read as Nightgrid stores them.

Two sources, both used as-is (no new format):

* **Nightgrid on this device**: the app's own database
  (~/.local/share/dev.nightgrid.Nightgrid/nightgrid.db), opened read-only. Nothing to
  set up. Saved passwords stay in the OS keychain and aren't read.
* **A profile export** (Settings -> Data -> Export / "Export profile..." in Nightgrid):
  the age file, decrypted once with its passphrase. Hosts, groups and, when the export
  included them, saved passwords are kept in this plugin's settings folder (0600).
"""
import json
import os
import sqlite3
import time

from . import agefile

APP_ID = "dev.nightgrid.Nightgrid"
FORMAT = "nightgrid-backup"
SECRET_KINDS = ("host-password", "key-passphrase", "sudo-password")
SKIP_DIRS = {"steamapps", "Steam", "node_modules", "compatdata", "shadercache", "homebrew", "Games", "Heroic"}


def app_data_dir(home: str) -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_ID)


def local_db(home: str):
    p = os.path.join(app_data_dir(home), "nightgrid.db")
    return p if os.path.isfile(p) else None


def _host(row: dict, groups: dict) -> dict:
    """One Nightgrid `hosts` row (database or export) -> what the plugin needs."""
    def s(k):
        v = row.get(k)
        return v.strip() if isinstance(v, str) and v.strip() else None
    try:
        port = int(row.get("port") or 22)
    except (TypeError, ValueError):
        port = 22
    return {
        "id": int(row["id"]),
        "name": s("name") or s("hostname") or f"host {row['id']}",
        "hostname": s("hostname") or "",
        "port": port if 0 < port < 65536 else 22,
        "username": s("username"),
        "auth": s("auth_method") or "agent",
        "identity": s("identity_file"),
        "proxyJump": s("proxy_jump"),
        "alias": s("ssh_alias"),
        "tailnet": s("tailnet_address"),
        "mac": s("mac_address"),
        "wakeRelay": row.get("wake_relay_id"),
        "sleepWindow": s("sleep_window"),
        "role": s("role") or "server",
        "os": s("os") or "",
        "group": groups.get(row.get("group_id")),
        "favorite": bool(row.get("favorite")),
        "order": row.get("sort_order") or 0,
    }


def _sort(hosts: list) -> list:
    return sorted(hosts, key=lambda h: (not h["favorite"], h["group"] or "", h["order"], h["name"].lower()))


def from_rows(host_rows: list, group_rows: list) -> list:
    groups = {g.get("id"): g.get("name") for g in group_rows if g.get("id") is not None}
    out = []
    for r in host_rows:
        try:
            out.append(_host(r, groups))
        except (KeyError, TypeError, ValueError):
            continue
    return _sort(out)


def read_local(home: str) -> dict:
    """Hosts from Nightgrid's own database on this device (read-only)."""
    path = local_db(home)
    if not path:
        raise FileNotFoundError("Nightgrid isn't installed on this device")
    last = None
    for mode in ("ro", "ro&immutable=1"):  # immutable: no -shm writes when the folder is read-only
        try:
            con = sqlite3.connect(f"file:{path}?mode={mode}", uri=True, timeout=2)
            con.row_factory = sqlite3.Row
            try:
                hosts = [dict(r) for r in con.execute("SELECT * FROM hosts")]
                groups = [dict(r) for r in con.execute("SELECT id, name FROM host_groups")]
            finally:
                con.close()
            return {"hosts": from_rows(hosts, groups), "secrets": {}, "mtime": os.path.getmtime(path)}
        except sqlite3.Error as e:
            last = e
    raise RuntimeError(f"couldn't read Nightgrid's database: {last}")


def read_export(data: bytes, passphrase: str) -> dict:
    """Decrypts a Nightgrid profile export and returns hosts + host secrets."""
    raw = agefile.decrypt(data, passphrase)
    try:
        b = json.loads(raw)
    except ValueError:
        raise agefile.AgeError("not a Nightgrid profile (unexpected contents)")
    if not isinstance(b, dict) or b.get("format") != FORMAT:
        raise agefile.AgeError("not a Nightgrid profile")
    tables = b.get("tables") or {}
    hosts = from_rows(tables.get("hosts") or [], tables.get("host_groups") or [])
    ids = {h["id"] for h in hosts}
    secrets = {}
    for s in b.get("secrets") or []:
        if not isinstance(s, dict) or s.get("owner") != "host" or s.get("kind") not in SECRET_KINDS:
            continue
        hid, val = s.get("id"), s.get("value")
        if isinstance(hid, int) and hid in ids and isinstance(val, str) and val:
            secrets.setdefault(str(hid), {})[s["kind"]] = val
    return {
        "hosts": hosts,
        "secrets": secrets,
        "appVersion": b.get("appVersion"),
        "createdAt": b.get("createdAt"),
    }


def candidate_dirs(home: str, user: str):
    names = ["", "Downloads", "Documents", "Desktop", "Nightgrid", "Sync", "Syncthing", "Dropbox",
             "Nextcloud", "OneDrive", "Google Drive"]
    seen = set()
    for n in names:
        p = os.path.join(home, n) if n else home
        if os.path.isdir(p) and p not in seen:
            seen.add(p)
            yield p, (0 if not n else 2)
    for media in (os.path.join("/run/media", user), "/run/media", "/media"):
        try:
            for e in os.scandir(media):
                if e.is_dir(follow_symlinks=False) and e.path not in seen and e.name != user:
                    seen.add(e.path)
                    yield e.path, 2
        except OSError:
            pass


def find_exports(home: str, user: str, limit: int = 40) -> list:
    """Passphrase-encrypted age files that look like Nightgrid profiles, newest first."""
    found = {}
    budget = [4000]  # directory entries to look at in total; keeps this instant on big cards

    def walk(d, depth):
        try:
            it = list(os.scandir(d))
        except OSError:
            return
        for e in it:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            if e.name.startswith("."):
                continue
            try:
                if e.is_file(follow_symlinks=False) and e.name.endswith(".age"):
                    st = e.stat()
                    if 0 < st.st_size <= agefile.MAX_BYTES:
                        with open(e.path, "rb") as f:
                            if agefile.is_passphrase_file(f.read(64)):
                                found[e.path] = {"path": e.path, "name": e.name, "size": st.st_size,
                                                 "mtime": st.st_mtime}
                elif depth > 0 and e.is_dir(follow_symlinks=False) and e.name not in SKIP_DIRS:
                    walk(e.path, depth - 1)
            except OSError:
                continue

    for d, depth in candidate_dirs(home, user):
        walk(d, depth)
    return sorted(found.values(), key=lambda x: -x["mtime"])[:limit]


class Store:
    """The imported profile, kept in the plugin's settings folder."""

    def __init__(self, settings_dir: str):
        self.dir = settings_dir
        self.path = os.path.join(settings_dir, "profile.json")
        self.prefs_path = os.path.join(settings_dir, "prefs.json")

    def _write(self, path, obj):
        os.makedirs(self.dir, exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def load(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            return d if isinstance(d, dict) and isinstance(d.get("hosts"), list) else None
        except (OSError, ValueError):
            return None

    def save_export(self, file_path: str, parsed: dict):
        self._write(self.path, {
            "source": "file",
            "file": file_path,
            "importedAt": time.time(),
            "appVersion": parsed.get("appVersion"),
            "createdAt": parsed.get("createdAt"),
            "hosts": parsed["hosts"],
            "secrets": parsed["secrets"],
        })

    def forget(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def prefs(self) -> dict:
        d = {"interval": 15, "showClients": False}
        try:
            with open(self.prefs_path) as f:
                v = json.load(f)
            if isinstance(v, dict):
                d.update({k: v[k] for k in d if k in v})
        except (OSError, ValueError):
            pass
        return d

    def set_prefs(self, patch: dict) -> dict:
        d = self.prefs()
        if "interval" in patch and patch["interval"] in (10, 15, 30, 60):
            d["interval"] = patch["interval"]
        if "showClients" in patch:
            d["showClients"] = bool(patch["showClients"])
        self._write(self.prefs_path, d)
        return d
