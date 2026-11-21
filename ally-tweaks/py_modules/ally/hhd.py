"""Minimal client for Handheld Daemon's local API (root-only UNIX socket).

Same transport hhdctl uses (hhd/http/ctl.py): HTTP over /run/hhd/api,
GET/POST /api/v1/state with flat dotted keys. HHD validates and applies the
values itself and saves them to its own state file, so anything written here
keeps working when Decky or this plugin is not loaded.
"""
import json
import os
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
    try:
        con.request(method, "/api/v1/state", body=json.dumps(body) if body is not None else None,
                    headers={"Content-Type": "application/json"} if body is not None else {})
        res = con.getresponse()
        data = res.read()
    finally:
        con.close()
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
    return os.path.exists(SOCKET)


def get_state() -> dict:
    return _flat(_request("GET"))


def set_state(values: dict) -> dict:
    return _flat(_request("POST", values))


def set_changed(values: dict, state: dict | None = None) -> bool:
    """Writes only keys whose value differs. Returns True if anything was sent."""
    st = state if state is not None else get_state()
    diff = {k: v for k, v in values.items() if st.get(k) != v}
    if not diff:
        return False
    set_state(diff)
    return True
