"""ProtonDB community ratings.

Uses the public summaries endpoint the ProtonDB site and other tools use:
  https://www.protondb.com/api/v1/reports/summaries/<appid>.json
Fields: tier, bestReportedTier, trendingTier, confidence, score, total
(and provisionalTier for new games). 404 = no reports yet.

ProtonDB has no public per-report API, so we can't read which Proton
version reporters used. The recommendation is tier-driven (see frontend
recommend.ts).
"""
import json
import os
import time
import urllib.error

import decky

from . import net

URL = "https://www.protondb.com/api/v1/reports/summaries/{}.json"
CACHE = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "protondb-cache.json")
TTL_OK = 3 * 86400
TTL_MISS = 86400

_mem: dict = {}
_loaded = False


def _load():
    global _loaded, _mem
    if _loaded:
        return
    _loaded = True
    try:
        with open(CACHE, "r", encoding="utf-8") as f:
            _mem = json.load(f)
    except Exception:
        _mem = {}


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_mem, f)
        os.replace(tmp, CACHE)
    except Exception as e:
        decky.logger.warning(f"protondb cache save failed: {e}")


def summary(appid: str, force: bool = False):
    _load()
    appid = str(appid)
    hit = _mem.get(appid)
    if hit and not force:
        ttl = TTL_OK if hit.get("data") else TTL_MISS
        if time.time() - hit.get("at", 0) < ttl:
            return hit.get("data")
    try:
        raw = net.get_json(URL.format(appid), timeout=10)
        data = {k: raw.get(k) for k in
                ("tier", "bestReportedTier", "trendingTier", "provisionalTier", "confidence", "score", "total")}
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        data = None
    _mem[appid] = {"at": time.time(), "data": data}
    _save()
    return data
