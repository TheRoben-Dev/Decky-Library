"""Small JSON files, written atomically. Only touched when something changes."""
import json
import os
import tempfile


def read_json(path: str, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, type(fallback)) else fallback
    except FileNotFoundError:
        return fallback
    except Exception:
        # A broken file shouldn't brick the plugin; it is rewritten on the next save.
        return fallback


def write_json(path: str, data, private: bool = False) -> None:
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


SETTINGS = {
    "auth": {},                # GOG tokens {access_token, refresh_token, expires, user_id}; never sent to the UI
    "user": {},                # {id, username} of the signed-in account
    "root": "",                # install folder; "" = ~/Games/gog
    "prefer": "linux",         # "linux" = native builds first, "windows" = Windows builds first
    "tool": "",                # Proton tool for Windows builds; "" = newest Proton Steam has
    "language": "en-US",       # game language (Galaxy depots / installers)
    "art": "gog",              # Steam artwork: "gog" = GOG's own covers, "nightgrid" = drawn in the Nightgrid look
    "keep_downloads": False,   # keep downloaded installers after installing
    "country": "US",           # store prices
    "currency": "USD",
}


class Settings:
    def __init__(self, path: str):
        self.path = path
        self.data = json.loads(json.dumps(SETTINGS))
        saved = read_json(path, {})
        for k, v in saved.items():
            if k in SETTINGS and type(v) is type(SETTINGS[k]):
                self.data[k] = v

    def save(self) -> None:
        write_json(self.path, self.data, private=True)   # holds the GOG tokens

    def public(self) -> dict:
        d = {k: v for k, v in self.data.items() if k != "auth"}
        d["signedIn"] = bool(self.data["auth"].get("refresh_token"))
        return d


class Installed:
    """game id -> install record. One file, small (a few hundred bytes per game)."""

    def __init__(self, path: str):
        self.path = path
        raw = read_json(path, {})
        self.games = {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def save(self) -> None:
        write_json(self.path, self.games)

    def get(self, game_id) -> dict | None:
        return self.games.get(str(int(game_id)))

    def put(self, game_id, rec: dict) -> None:
        self.games[str(int(game_id))] = rec
        self.save()

    def drop(self, game_id) -> None:
        self.games.pop(str(int(game_id)), None)
        self.save()
