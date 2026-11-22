"""Settings file (JSON, written atomically). Only touched when the user changes something."""
import json
import os
import tempfile

DEFAULTS = {
    "key": "",
    "nsfw": False,
    "humor": True,
    "epilepsy": False,
    "animated": False,
    "styles": {"grids": [], "heroes": [], "logos": [], "icons": []},
    # appid -> {kind: sgdb asset id} for the art this plugin applied, so the browser can mark it.
    "applied": {},
    # appid -> {"id": sgdb game id, "name": str} picked with the custom search; overrides auto-detect.
    "matches": {},
}


class Store:
    def __init__(self, path: str):
        self.path = path
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                        self.data[k] = v
        except FileNotFoundError:
            pass
        except Exception:
            # A broken file shouldn't brick the plugin; it is rewritten on the next save.
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".settings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.chmod(tmp, 0o600)   # holds the API key
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def public(self) -> dict:
        """Settings for the frontend; the key itself never leaves the backend."""
        d = {k: v for k, v in self.data.items() if k not in ("key", "applied", "matches")}
        k = self.data["key"]
        d["hasKey"] = bool(k)
        d["keyHint"] = f"…{k[-4:]}" if len(k) >= 8 else ""
        return d
