"""One TLS context for every HTTPS call the plugin makes itself (Legendary runs in system Python
and has its own). Decky's frozen Python doesn't find the system CA store on its own, which fails
with CERTIFICATE_VERIFY_FAILED, so point it at the distro bundle (Bazzite/Fedora first), then
certifi if it's importable. Verification is never turned off."""
import os
import ssl

CA_FILES = ("/etc/pki/tls/certs/ca-bundle.crt",        # Fedora / Bazzite
            "/etc/ssl/certs/ca-certificates.crt",      # Arch / SteamOS / Debian
            "/etc/ssl/cert.pem")
_ctx = None


def context() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        _ctx = _build()
    return _ctx


def _build() -> ssl.SSLContext:
    for f in CA_FILES:
        if os.path.isfile(f):
            try:
                return ssl.create_default_context(cafile=f)
            except (OSError, ssl.SSLError):
                continue
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
