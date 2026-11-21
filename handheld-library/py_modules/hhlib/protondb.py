"""ProtonDB tier lookup with an on-disk cache.

Only the public summary endpoint is used: https://www.protondb.com/api/v1/reports/summaries/<appid>.json
(returns {"tier": "platinum" | "gold" | "silver" | "bronze" | "borked" | "pending", ...}; 404 when a game
has no reports). Results are cached for CACHE_DAYS so a library sync doesn't hit ProtonDB every time.
"""
import asyncio
import json
import os
import ssl
import time
import urllib.error
import urllib.request

URL = "https://www.protondb.com/api/v1/reports/summaries/{}.json"
UA = "handheld-library-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"
CACHE_DAYS = 7
NONE_TIER = "none"          # cached marker: ProtonDB has no reports for this app
TIERS = ("borked", "bronze", "silver", "gold", "platinum")
MAX_PARALLEL = 4
MAX_PER_SYNC = 400          # keeps one sync from firing thousands of requests

_CA_FILES = (
    "/etc/pki/tls/certs/ca-bundle.crt",      # Fedora / Bazzite
    "/etc/ssl/certs/ca-certificates.crt",    # Arch / SteamOS / Debian
    "/etc/ssl/cert.pem",
)
_ctx = None


def _context() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        try:
            import certifi  # type: ignore
            _ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            f = next((f for f in _CA_FILES if os.path.exists(f)), None)
            _ctx = ssl.create_default_context(cafile=f) if f else ssl.create_default_context()
    return _ctx


def tier_rank(tier: str) -> int:
    """-1 for unknown/none/pending, else 0 (borked) .. 4 (platinum)."""
    try:
        return TIERS.index((tier or "").lower())
    except ValueError:
        return -1


class Cache:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.data = {str(k): v for k, v in raw.items() if isinstance(v, list) and len(v) == 2}
        except (OSError, ValueError):
            pass

    def get(self, appid: int, now: float):
        v = self.data.get(str(appid))
        if v and now - v[1] < CACHE_DAYS * 86400:
            return v[0]
        return None

    def put(self, appid: int, tier: str, now: float):
        self.data[str(appid)] = [tier, now]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)


def _fetch_one(appid: int) -> str:
    req = urllib.request.Request(URL.format(int(appid)), headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_context()) as r:
            body = json.loads(r.read(64 * 1024).decode("utf-8", "replace"))
        tier = str(body.get("tier") or "").lower()
        return tier if tier in TIERS or tier == "pending" else NONE_TIER
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return NONE_TIER
        raise


async def lookup(cache: Cache, appids, log=None) -> dict:
    """{appid: tier} for every appid; fetches what isn't cached (bounded), errors leave the app out."""
    now = time.time()
    out, todo = {}, []
    for a in dict.fromkeys(int(x) for x in appids):
        t = cache.get(a, now)
        if t is None:
            todo.append(a)
        else:
            out[a] = t
    todo = todo[:MAX_PER_SYNC]
    sem = asyncio.Semaphore(MAX_PARALLEL)
    errors = 0

    async def one(a):
        nonlocal errors
        async with sem:
            try:
                t = await asyncio.to_thread(_fetch_one, a)
            except Exception as e:  # network down, rate limit, etc.: try again next sync
                errors += 1
                if log and errors <= 3:
                    log(f"ProtonDB lookup for {a} failed: {e}")
                return
            cache.put(a, t, now)
            out[a] = t

    await asyncio.gather(*(one(a) for a in todo))
    if todo:
        try:
            cache.save()
        except OSError as e:
            if log:
                log(f"could not save ProtonDB cache: {e}")
    return out
