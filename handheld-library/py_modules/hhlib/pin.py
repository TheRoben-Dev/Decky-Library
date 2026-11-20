"""PIN lock for the Hidden games tab.

Privacy lock, not security: it keeps casual eyes off the tab. The PIN is stored only as a salted
PBKDF2-HMAC-SHA256 hash in pin.json in the plugin's settings folder; deleting that file (e.g. from
Desktop Mode) removes the lock. A wrong PIN just fails; there is no lockout (user's choice).
"""
import hashlib
import hmac
import json
import os
import re
import secrets

ITERATIONS = 200_000
_PIN = re.compile(r"^\d{4,8}$")


def valid_pin(pin) -> bool:
    return isinstance(pin, str) and bool(_PIN.match(pin))


def _hash(pin: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)


class PinStore:
    def __init__(self, path: str):
        self.path = path

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and all(k in d for k in ("salt", "hash", "iterations")):
                return d
        except (OSError, ValueError):
            pass
        return None

    def _write(self, d):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, self.path)

    def is_set(self) -> bool:
        return self._load() is not None

    def status(self) -> dict:
        return {"set": self.is_set(), "retryIn": 0}

    def verify(self, pin) -> dict:
        """{"ok": bool, "retryIn": seconds}. No PIN set → always ok."""
        d = self._load()
        if d is None:
            return {"ok": True, "retryIn": 0}
        ok = False
        if isinstance(pin, str):
            try:
                want = bytes.fromhex(d["hash"])
                got = _hash(pin, bytes.fromhex(d["salt"]), int(d["iterations"]))
                ok = hmac.compare_digest(want, got)
            except (ValueError, TypeError):
                ok = False
        return {"ok": ok, "retryIn": 0}

    def set(self, new, current=None) -> dict:
        if not valid_pin(new):
            return {"ok": False, "error": "The PIN must be 4 to 8 digits."}
        if self.is_set():
            r = self.verify(current)
            if not r["ok"]:
                return {"ok": False, "error": "Current PIN is wrong.", "retryIn": r["retryIn"]}
        salt = secrets.token_bytes(16)
        self._write({"salt": salt.hex(), "hash": _hash(new, salt, ITERATIONS).hex(), "iterations": ITERATIONS})
        return {"ok": True}

    def clear(self, current) -> dict:
        if not self.is_set():
            return {"ok": True}
        r = self.verify(current)
        if not r["ok"]:
            return {"ok": False, "error": "Current PIN is wrong.", "retryIn": r["retryIn"]}
        try:
            os.remove(self.path)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}
