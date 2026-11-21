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
    "root": "",                # install folder; "" = ~/Games/epic
    "tool": "",                # Proton tool for Epic games; "" = newest Proton Steam has
    "dlcs": True,              # install the DLC you own together with the game
    "show_all": False,         # also list games that need another launcher (EA app, Ubisoft Connect)
}


class Settings:
    """Plugin options. The Epic sign-in itself lives in Legendary's own folder, not here."""

    def __init__(self, path: str):
        self.path = path
        self.data = json.loads(json.dumps(SETTINGS))
        saved = read_json(path, {})
        for k, v in saved.items():
            if k in SETTINGS and type(v) is type(SETTINGS[k]):
                self.data[k] = v

    def save(self) -> None:
        write_json(self.path, self.data)


class Meta:
    """app name -> what this plugin adds to a Legendary install: the Steam shortcut appid, and the
    folder of a cancelled download (so it can be resumed or discarded). Small, one file."""

    def __init__(self, path: str):
        self.path = path
        raw = read_json(path, {})
        self.games = {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def save(self) -> None:
        write_json(self.path, self.games)

    def get(self, app: str) -> dict:
        return dict(self.games.get(app) or {})

    def update(self, app: str, **kw) -> dict:
        rec = {**(self.games.get(app) or {}), **kw}
        rec = {k: v for k, v in rec.items() if v not in (None, "", 0)}
        if rec:
            self.games[app] = rec
        else:
            self.games.pop(app, None)
        self.save()
        return rec

    def drop(self, app: str) -> None:
        if self.games.pop(app, None) is not None:
            self.save()
