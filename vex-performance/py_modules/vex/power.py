"""Direct sysfs fallback for when Handheld Daemon is NOT running.

TDP: asus-armoury firmware attributes (newer kernels) or legacy asus-nb-wmi.
GPU: amdgpu pp_od_clk_voltage manual range.
"""
import glob
import os
import time

ARMOURY = "/sys/class/firmware-attributes/asus-armoury/attributes"
TDP_SETS = [
    [f"{ARMOURY}/ppt_pl1_spl/current_value", f"{ARMOURY}/ppt_pl2_sppt/current_value",
     f"{ARMOURY}/ppt_pl3_fppt/current_value", f"{ARMOURY}/ppt_fppt/current_value"],
    ["/sys/devices/platform/asus-nb-wmi/ppt_pl1_spl", "/sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt",
     "/sys/devices/platform/asus-nb-wmi/ppt_fppt"],
]


def _write(path, value):
    with open(path, "w") as f:
        f.write(str(value))


def _read(path):
    with open(path) as f:
        return f.read().strip()


def _gpu_dev():
    for card in sorted(glob.glob("/sys/class/drm/card*/device")):
        if os.path.exists(f"{card}/pp_od_clk_voltage") and os.path.exists(
            f"{card}/power_dpm_force_performance_level"
        ):
            return card
    return None


def gpu_range():
    dev = _gpu_dev()
    if not dev:
        return None
    try:
        lines = _read(f"{dev}/pp_od_clk_voltage").splitlines()
        in_range = False
        for line in lines:
            if line.startswith("OD_RANGE"):
                in_range = True
                continue
            if in_range and line.strip().startswith("SCLK"):
                parts = line.replace("Mhz", "").replace("MHz", "").split()
                return [int(parts[1]), int(parts[2])]
    except Exception:
        pass
    return None


def tdp_paths():
    for group in TDP_SETS:
        found = [p for p in group if os.path.exists(p)]
        if len(found) >= 3:
            return found
    return None


def capabilities():
    paths = tdp_paths()
    tdp_min = tdp_max = None
    if paths and paths[0].startswith(ARMOURY):
        base = os.path.dirname(paths[0])
        try:
            tdp_min = int(_read(f"{base}/min_value"))
            tdp_max = int(_read(f"{base}/max_value"))
        except Exception:
            pass
    return {
        "sysfsTdp": bool(paths),
        "tdpMin": tdp_min,
        "tdpMax": tdp_max,
        "gpuRange": gpu_range(),
    }


def set_tdp_sysfs(watts: int):
    paths = tdp_paths()
    if not paths:
        return "no-sysfs-tdp"
    for p in paths:
        _write(p, int(watts))
        time.sleep(0.05)
    return "ok"


def set_gpu_sysfs(mode: str, gmin: int, gmax: int):
    dev = _gpu_dev()
    if not dev:
        return "no-gpu-sysfs"
    level = f"{dev}/power_dpm_force_performance_level"
    if mode == "auto":
        if _read(level) != "auto":
            _write(level, "auto")
        return "ok"
    rng = gpu_range() or [gmin, gmax]
    lo = rng[0] if mode == "max" else (gmax if mode == "fixed" else gmin)
    hi = gmax
    lo, hi = max(rng[0], min(lo, hi)), min(rng[1], hi)
    _write(level, "manual")
    time.sleep(0.05)
    od = f"{dev}/pp_od_clk_voltage"
    _write(od, f"s 0 {lo}")
    _write(od, f"s 1 {hi}")
    _write(od, "c")
    return "ok"
