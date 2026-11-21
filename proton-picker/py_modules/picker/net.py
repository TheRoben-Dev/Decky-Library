"""HTTP helpers. Decky's bundled Python may not find the system CA store on
its own, so we try certifi, then the distro bundles (Fedora/Bazzite first)."""
import json
import os
import ssl
import urllib.request

UA = "proton-picker-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"

_CA_FILES = [
    "/etc/pki/tls/certs/ca-bundle.crt",      # Fedora / Bazzite
    "/etc/ssl/certs/ca-certificates.crt",    # Arch / SteamOS / Debian
    "/etc/ssl/cert.pem",
]
_ctx = None


def context() -> ssl.SSLContext:
    global _ctx
    if _ctx:
        return _ctx
    try:
        import certifi  # type: ignore
        _ctx = ssl.create_default_context(cafile=certifi.where())
        return _ctx
    except Exception:
        pass
    for f in _CA_FILES:
        if os.path.exists(f):
            _ctx = ssl.create_default_context(cafile=f)
            return _ctx
    _ctx = ssl.create_default_context()
    return _ctx


def open_url(url: str, timeout: float = 20, accept: str = "*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    return urllib.request.urlopen(req, timeout=timeout, context=context())


def get_json(url: str, timeout: float = 20):
    with open_url(url, timeout, "application/json") as r:
        return json.loads(r.read().decode("utf-8"))


def get_text(url: str, timeout: float = 20) -> str:
    with open_url(url, timeout) as r:
        return r.read().decode("utf-8", "replace")
