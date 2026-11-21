"""LEGACY: Handheld Daemon was retired in Bazzite 44 (replaced by InputPlumber,
steamos-manager and PowerStation). Kept only as an opt-in path for older images.

Minimal client for Handheld Daemon's local API (root-only UNIX socket).

Same transport hhdctl uses: HTTP over /run/hhd/api, POST /api/v1/state with
flat dotted keys. We only touch TDP and GPU-frequency keys.
"""
import json
import socket
from http.client import HTTPConnection

SOCKET = "/run/hhd/api"


class _UnixConnection(HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(SOCKET)


def _request(method, body=None):
    con = _UnixConnection("localhost", timeout=5)
    con.request(method, "/api/v1/state", body=json.dumps(body) if body is not None else None,
                headers={"Content-Type": "application/json"} if body is not None else {})
    res = con.getresponse()
    data = res.read()
    if res.status != 200:
        raise RuntimeError(f"HHD returned {res.status}")
    return json.loads(data)


def _flat(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = d
    return out


def available() -> bool:
    try:
        import os
        return os.path.exists(SOCKET)
    except Exception:
        return False


def get_state() -> dict:
    return _flat(_request("GET"))


def set_state(values: dict) -> dict:
    return _flat(_request("POST", values))


def _tdp_prefix(state: dict):
    """Device TDP container differs per vendor: tdp.asus, tdp.legion, tdp.smu..."""
    for key in state:
        if key.startswith("tdp.") and key.endswith(".tdp_v2.mode"):
            return key[: -len(".tdp_v2.mode")], "v2"
    if "tdp.qam.tdp" in state:
        return "tdp.qam", "qam"
    return None, None


def status() -> dict:
    if not available():
        return {"running": False}
    try:
        st = get_state()
        prefix, kind = _tdp_prefix(st)
        return {
            "running": True,
            "tdpEnabled": bool(st.get("hhd.settings.tdp_enable", False)),
            "tdpPrefix": prefix,
            "tdpKind": kind,
            "gpuControl": "tdp.amd_energy.gpu_freq.mode" in st,
            "steamFuse": bool(st.get("hhd.settings.fuse_mount", False)),
        }
    except Exception as e:
        return {"running": True, "error": str(e)}


def set_tdp(watts: int):
    st = get_state()
    prefix, kind = _tdp_prefix(st)
    if not st.get("hhd.settings.tdp_enable", False):
        return "hhd-tdp-disabled"
    if kind == "v2":
        set_state({f"{prefix}.tdp_v2.mode": "custom", f"{prefix}.tdp_v2.custom.tdp": int(watts)})
        return "ok"
    if kind == "qam":
        set_state({"tdp.qam.tdp": int(watts)})
        return "ok"
    return "no-tdp-key"


def set_gpu(mode: str, gmin: int, gmax: int):
    st = get_state()
    if "tdp.amd_energy.gpu_freq.mode" not in st:
        return "no-gpu-control"
    if mode == "max":
        vals = {"tdp.amd_energy.gpu_freq.mode": "upper",
                "tdp.amd_energy.gpu_freq.upper.frequency": int(gmax)}
    elif mode in ("fixed", "range"):
        lo = int(gmax if mode == "fixed" else gmin)
        vals = {"tdp.amd_energy.gpu_freq.mode": "range",
                "tdp.amd_energy.gpu_freq.range.min": lo,
                "tdp.amd_energy.gpu_freq.range.max": int(gmax)}
    else:
        vals = {"tdp.amd_energy.gpu_freq.mode": "auto"}
    if st.get("tdp.amd_energy.gpu_freq.mode") == vals["tdp.amd_energy.gpu_freq.mode"] and all(
        st.get(k) == v for k, v in vals.items()
    ):
        return "unchanged"
    set_state(vals)
    return "ok"
