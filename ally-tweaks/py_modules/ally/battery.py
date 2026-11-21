"""Battery health + charge limit.

Charge limit goes through Handheld Daemon when it exposes it
(gamemode.battery.charge_limit, adjustor/drivers/battery), because HHD
re-applies it on every boot and would otherwise overwrite ours. Without HHD it
writes the kernel's documented power_supply attribute
charge_control_end_threshold (provided by asus-wmi on the Ally) directly and
the plugin re-applies it on load.
"""
import os

from . import hhd

PS = "/sys/class/power_supply"
LIMITS = (70, 80, 85, 90, 95, 100)
HHD_KEY = "gamemode.battery.charge_limit"


def _read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


def _int(path):
    v = _read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def battery_dir():
    try:
        for name in sorted(os.listdir(PS)):
            if name.startswith("BAT") and _read(f"{PS}/{name}/type") == "Battery":
                return f"{PS}/{name}"
    except Exception:
        pass
    return None


def ac_online():
    try:
        for name in os.listdir(PS):
            if _read(f"{PS}/{name}/type") == "Mains":
                return _read(f"{PS}/{name}/online") == "1"
    except Exception:
        pass
    # Fall back to battery status
    b = battery_dir()
    return bool(b) and _read(f"{b}/status") in ("Charging", "Full", "Not charging")


def snapshot() -> dict:
    b = battery_dir()
    if not b:
        return {"present": False}
    full = _int(f"{b}/energy_full") or _int(f"{b}/charge_full")
    design = _int(f"{b}/energy_full_design") or _int(f"{b}/charge_full_design")
    power = _int(f"{b}/power_now")
    if power is None:
        cur, volt = _int(f"{b}/current_now"), _int(f"{b}/voltage_now")
        power = (cur * volt // 1_000_000) if cur is not None and volt is not None else None
    return {
        "present": True,
        "capacity": _int(f"{b}/capacity"),
        "status": _read(f"{b}/status", "Unknown"),
        "ac": ac_online(),
        "cycles": _int(f"{b}/cycle_count"),
        "health": round(full * 100 / design, 1) if full and design else None,
        "watts": round(abs(power) / 1_000_000, 1) if power else None,
        "threshold": _int(f"{b}/charge_control_end_threshold"),
        "thresholdSupported": os.path.exists(f"{b}/charge_control_end_threshold"),
    }


def _nearest(limit: int) -> int:
    return min(LIMITS, key=lambda x: abs(x - int(limit)))


def backend(state: dict | None) -> str:
    if state is not None and HHD_KEY in state:
        return "hhd"
    b = battery_dir()
    if b and os.path.exists(f"{b}/charge_control_end_threshold"):
        return "sysfs"
    return "none"


def set_limit(limit: int, state: dict | None = None) -> str:
    limit = _nearest(limit)
    be = backend(state)
    if be == "hhd":
        val = "disabled" if limit >= 100 else f"p{limit}"
        hhd.set_changed({HHD_KEY: val}, state)
        return "hhd"
    if be == "sysfs":
        path = f"{battery_dir()}/charge_control_end_threshold"
        if _int(path) != limit:
            with open(path, "w") as f:
                f.write(f"{limit}\n")
        return "sysfs"
    return "none"
