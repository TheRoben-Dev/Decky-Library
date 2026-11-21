"""Read-only temperature for the reactive RGB mode (k10temp Tctl)."""
import os

HWMON = "/sys/class/hwmon"
_cached = None


def _find():
    global _cached
    if _cached and os.path.exists(_cached):
        return _cached
    try:
        for d in os.listdir(HWMON):
            base = f"{HWMON}/{d}"
            try:
                with open(f"{base}/name") as f:
                    name = f.read().strip()
            except Exception:
                continue
            if name == "k10temp":
                _cached = f"{base}/temp1_input"
                return _cached
    except Exception:
        pass
    return None


def apu_temp():
    p = _find()
    if not p:
        return None
    try:
        with open(p) as f:
            return int(f.read().strip()) / 1000
    except Exception:
        return None
