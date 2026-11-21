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
    "auth": {},                # device tokens + serial + user (never sent to the frontend)
    "login": {},               # pending sign-in (PKCE verifier, serial) until it's finished
    "root": "",                # install folder; "" = ~/Games/amazon
    "tool": "",                # Proton tool; "" = newest Proton Steam has
}
SECRET = ("auth", "login")


class Settings:
    def __init__(self, path: str):
        self.path = path
        self.data = json.loads(json.dumps(SETTINGS))
        saved = read_json(path, {})
        for k, v in saved.items():
            if k in SETTINGS and type(v) is type(SETTINGS[k]):
                self.data[k] = v

    def save(self) -> None:
        write_json(self.path, self.data, private=True)   # holds the tokens

    def public(self) -> dict:
        d = {k: v for k, v in self.data.items() if k not in SECRET}
        auth = self.data["auth"]
        d["signedIn"] = bool(auth.get("refresh_token"))
        d["user"] = auth.get("user") or {}
        return d


class Installed:
    """product id -> install record. One file, small (a few hundred bytes per game)."""

    def __init__(self, path: str):
        self.path = path
        raw = read_json(path, {})
        self.games = {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def save(self) -> None:
        write_json(self.path, self.games)

    def get(self, game_id) -> dict | None:
        return self.games.get(str(game_id))

    def put(self, game_id, rec: dict) -> None:
        self.games[str(game_id)] = rec
        self.save()

    def drop(self, game_id) -> None:
        self.games.pop(str(game_id), None)
        self.save()
