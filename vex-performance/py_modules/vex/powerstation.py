"""PowerStation client (ShadowBlip), the power daemon Bazzite 44+ ships in
place of Handheld Daemon. System D-Bus, bus name org.shadowblip.PowerStation:

  /org/shadowblip/Performance/GPU            org.shadowblip.GPU.EnumerateCards() -> ao
  <card>   org.shadowblip.GPU.Card           ManualClock b, ClockValueMhzMin/Max d,
                                             ClockLimitMhzMin/Max d (read-only)
  <card>   org.shadowblip.GPU.Card.TDP       TDP d, Boost d, PowerProfile s

We talk to it with `busctl` (always present with systemd) so the plugin needs
no Python D-Bus bindings.
"""
import json
import os
import shutil
import subprocess


def _env():
    # Decky's bundled Python sets LD_LIBRARY_PATH to its own libs, which can break
    # system binaries like busctl (libsystemd/libc mismatches). Run them clean.
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
    return env

BUS = "org.shadowblip.PowerStation"
GPU_PATH = "/org/shadowblip/Performance/GPU"
CARD = "org.shadowblip.GPU.Card"
TDP = "org.shadowblip.GPU.Card.TDP"


def _busctl(*args, timeout=4):
    exe = shutil.which("busctl") or "/usr/bin/busctl"
    r = subprocess.run([exe, "--system", "--json=short", *args],
                       capture_output=True, text=True, timeout=timeout, env=_env())
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"busctl exit {r.returncode}")
    out = r.stdout.strip()
    return json.loads(out) if out else None


def _cards():
    res = _busctl("call", BUS, GPU_PATH, "org.shadowblip.GPU", "EnumerateCards")
    data = res["data"][0] if res and res.get("data") else []
    return data


def _card():
    cards = _cards()
    if not cards:
        raise RuntimeError("PowerStation reports no GPU card")
    return cards[0]


def _get(path, iface, prop):
    return _busctl("get-property", BUS, path, iface, prop)["data"]


def _set(path, iface, prop, sig, value):
    v = ("true" if value else "false") if sig == "b" else str(value)
    subprocess_args = ["set-property", BUS, path, iface, prop, sig, v]
    exe = shutil.which("busctl") or "/usr/bin/busctl"
    r = subprocess.run([exe, "--system", *subprocess_args], capture_output=True, text=True, timeout=4, env=_env())
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"busctl exit {r.returncode}")


def available() -> bool:
    try:
        _cards()
        return True
    except Exception:
        return False


def status() -> dict:
    try:
        card = _card()
    except Exception as e:
        return {"running": False, "error": str(e)}
    info = {"running": True, "card": card, "tdp": None, "gpuRange": None}
    try:
        info["tdp"] = _get(card, TDP, "TDP")
    except Exception:
        info["tdpUnsupported"] = True
    try:
        info["gpuRange"] = [int(_get(card, CARD, "ClockLimitMhzMin")), int(_get(card, CARD, "ClockLimitMhzMax"))]
    except Exception:
        pass
    return info


def set_tdp(watts: int):
    card = _card()
    if abs(float(_get(card, TDP, "TDP")) - watts) < 0.5:
        return "unchanged"
    _set(card, TDP, "TDP", "d", float(watts))
    return "ok"


def set_gpu(mode: str, gmin: int, gmax: int):
    card = _card()
    if mode == "auto":
        if _get(card, CARD, "ManualClock"):
            _set(card, CARD, "ManualClock", "b", False)
        return "ok"
    lo_lim = int(_get(card, CARD, "ClockLimitMhzMin"))
    hi_lim = int(_get(card, CARD, "ClockLimitMhzMax"))
    hi = max(lo_lim, min(hi_lim, int(gmax)))
    lo = lo_lim if mode == "max" else (hi if mode == "fixed" else max(lo_lim, min(hi, int(gmin))))
    _set(card, CARD, "ManualClock", "b", True)
    # widen first so min/max never cross mid-update
    _set(card, CARD, "ClockValueMhzMin", "d", float(lo_lim))
    _set(card, CARD, "ClockValueMhzMax", "d", float(hi))
    _set(card, CARD, "ClockValueMhzMin", "d", float(lo))
    return "ok"
