"""HTTPS helpers. Decky's bundled Python may not find the system CA store on its own,
so try certifi, then the distro bundles (Fedora/Bazzite first). Certificate checks are
never disabled."""
import json
import os
import ssl
import urllib.parse
import urllib.request

UA = "library-hub-decky/0.1 (+https://github.com/TheRoben-Dev/Decky-Library)"

_CA_FILES = [
    "/etc/pki/tls/certs/ca-bundle.crt",      # Fedora / Bazzite
    "/etc/ssl/certs/ca-certificates.crt",    # Arch / SteamOS / Debian
    "/etc/ssl/cert.pem",
]
# Hosts a GitHub API call or release download may be served from (after redirects).
ALLOWED_HOSTS = (
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)
# Decky's plugin store index (only read to find CSS Loader's artifact + hash; Decky downloads it).
STORE_HOSTS = ("plugins.deckbrew.xyz",)
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


def check_url(url: str, hosts=ALLOWED_HOSTS) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in hosts:
        raise ValueError(f"refusing URL outside the allowed hosts: {url}")


def _opener(hosts):
    class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check_url(newurl, hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context()), _HttpsOnlyRedirect()
    )


def fetch(url: str, max_bytes: int, accept: str = "*/*", timeout: float = 30, hosts=ALLOWED_HOSTS) -> bytes:
    check_url(url, hosts)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with _opener(hosts).open(req, timeout=timeout) as r:
        check_url(r.geturl(), hosts)
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"download larger than {max_bytes} bytes: {url}")
    return data


def get_json(url: str, hosts=ALLOWED_HOSTS, max_bytes: int = 2_000_000):
    return json.loads(fetch(url, max_bytes, "application/vnd.github+json, application/json",
                            hosts=hosts).decode("utf-8"))
