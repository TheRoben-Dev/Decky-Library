"""A one-time sign-in page on the local network, shared by the store plugins (same file in each).

The sign-in screen shows a QR code for http://<handheld-ip>:<port>/<token>. The page lives only
while that screen asks for it, answers only on the random path, accepts one sign-in and closes
after it (or when it expires).

Why the phone sometimes couldn't open it: the server used a random port, and distributions with
a firewall (Bazzite and other Fedora-based systems run firewalld) drop incoming connections on
ports their zone doesn't allow. A plugin runs without root, so it can't open the firewall, but
firewalld lets anyone read its settings. So the page goes on a fixed port the zone already allows
(47615-47619, or any free port in an allowed range); when the zone allows none, the status says
so and gives the one command that fixes it for all the plugins. The address is taken from the
interface that carries the default route, skipping VPN, Tailscale and container interfaces.

Only modules Decky's bundled Python is known to ship are imported here (no secrets, xml, uuid).
"""
import base64
import html
import http.server
import ipaddress
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse

PORTS = range(47615, 47620)          # one firewall rule (47615-47619/tcp) covers every plugin
SKIP_IFACES = ("lo", "docker", "br-", "veth", "virbr", "tailscale", "ts", "zt", "wg", "tun", "tap",
               "waydroid", "podman", "cni", "flannel", "vnet", "lxc", "incus")
SBIN = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")

STYLE = """:root{color-scheme:dark}body{margin:0;background:#07080B;color:#E6EDF3;font:15px/1.5 ui-monospace,'JetBrains Mono',monospace;
background-image:linear-gradient(#1F2633 1px,transparent 1px),linear-gradient(90deg,#1F2633 1px,transparent 1px);background-size:40px 40px}
main{max-width:520px;margin:0 auto;padding:28px 18px}h1{font-size:18px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 4px}
.tag{color:#00E5FF;border:1px solid #00E5FF;padding:1px 6px;font-size:11px;letter-spacing:.1em}
p,li{color:#8B98A9}ol{padding-left:20px}a{color:#00E5FF}
textarea,input{width:100%;box-sizing:border-box;background:#0D0F14;border:1px solid #1F2633;color:#E6EDF3;padding:12px;font:inherit;margin:8px 0}
textarea{min-height:90px;resize:vertical}textarea:focus,input:focus{outline:none;border-color:#FF2A6D}
button{width:100%;padding:12px;background:#FF2A6D;color:#07080B;border:0;font:inherit;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
a.go{display:block;text-align:center;text-decoration:none;padding:12px;margin:10px 0 18px;border:1px solid #00E5FF;color:#00E5FF;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.ok{color:#2BFF88}.err{color:#FF9F1C}.note{font-size:12px;border-top:1px solid #1F2633;margin-top:22px;padding-top:12px}"""

NOTE = """<p class="note">Your browser may call this page <b>Not secure</b>: it is a one-time page served by your handheld
over your own Wi-Fi (there is no certificate for a local address). Nothing on it goes through the internet, and it closes
itself after you sign in.</p>"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="referrer" content="no-referrer"><title>{html.escape(title)} sign-in</title><style>{STYLE}</style></head>'
            f'<body><main><h1>{html.escape(title)}</h1><span class="tag">SIGN IN</span>{body}{NOTE}</main></body></html>')


# ------------------------------------------------------------------ system helpers

def _env() -> dict:
    """Decky's bundled Python sets LD_LIBRARY_PATH (and may set PYTHON*), which breaks system tools."""
    env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = ":".join(dict.fromkeys(list(SBIN) + env.get("PATH", "").split(":")))
    env["LC_ALL"] = "C"
    return env


def _which(cmd: str) -> str:
    return shutil.which(cmd, path=":".join(SBIN)) or ""


def _run(args: list, timeout: float = 4.0) -> tuple:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_env(), stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return -1, ""


def _private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 100.64/10 (Tailscale, carrier NAT) counts as private to ipaddress, but a phone on Wi-Fi can't reach it.
    return a.version == 4 and a.is_private and not a.is_loopback and not a.is_link_local \
        and a not in ipaddress.ip_network("100.64.0.0/10")


def _skip(iface: str) -> bool:
    return not iface or iface.startswith(SKIP_IFACES)


def lan_address() -> tuple:
    """(ip, interface) other devices on the local network reach this one at; ("", "") if offline.
    No packets are sent."""
    ip_cmd = _which("ip")
    if ip_cmd:
        rc, out = _run([ip_cmd, "-o", "-4", "route", "get", "192.0.2.1"])   # TEST-NET: only picks a route
        f = out.split()
        if rc == 0 and "src" in f and "dev" in f:
            src, dev = f[f.index("src") + 1], f[f.index("dev") + 1]
            if _private(src) and not _skip(dev):
                return src, dev
        # Default route is a VPN or similar: pick the Wi-Fi / Ethernet address instead.
        rc, out = _run([ip_cmd, "-o", "-4", "addr", "show", "up", "scope", "global"])
        best = None
        for line in out.splitlines():
            p = line.split()
            if len(p) < 4 or p[2] != "inet" or _skip(p[1]):
                continue
            addr = p[3].split("/")[0]
            if not _private(addr):
                continue
            rank = 0 if p[1].startswith(("wl", "en", "eth")) else 1
            if best is None or rank < best[0]:
                best = (rank, addr, p[1])
        if best:
            return best[1], best[2]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        addr = s.getsockname()[0]
        return (addr, "") if addr and not addr.startswith("127.") else ("", "")
    except OSError:
        return "", ""
    finally:
        s.close()


def _tcp_ranges(text: str) -> list:
    out = []
    for item in text.split():
        port, _, proto = item.partition("/")
        if proto != "tcp":
            continue
        a, _, b = port.partition("-")
        try:
            out.append((int(a), int(b or a)))
        except ValueError:
            pass
    return out


def _fields(text: str) -> dict:
    d = {}
    for line in text.splitlines():
        k, sep, v = line.strip().partition(":")
        if sep and k and k not in d:
            d[k] = v.strip()
    return d


def firewall(iface: str) -> dict:
    """What firewalld lets in on this interface. state: off (no firewalld), open (everything),
    filtered (only `ranges`), unknown (couldn't read it)."""
    fw = _which("firewall-cmd")
    if not fw:
        return {"state": "off", "zone": ""}
    rc, _ = _run([fw, "--state"])
    if rc != 0:
        return {"state": "off" if rc == 252 else "unknown", "zone": ""}   # 252: firewalld not running
    zone = ""
    if iface:
        rc, out = _run([fw, f"--get-zone-of-interface={iface}"])
        zone = out if rc == 0 else ""
    if not zone:
        rc, out = _run([fw, "--get-default-zone"])
        zone = out if rc == 0 else ""
    if not zone:
        return {"state": "unknown", "zone": ""}
    rc, out = _run([fw, f"--zone={zone}", "--list-all"])
    if rc != 0:
        return {"state": "unknown", "zone": zone}
    d = _fields(out)
    if d.get("target", "").upper() == "ACCEPT":
        return {"state": "open", "zone": zone}
    ranges = _tcp_ranges(d.get("ports", ""))
    for svc in d.get("services", "").split()[:24]:
        rc, sout = _run([fw, f"--info-service={svc}"])
        if rc == 0:
            ranges += _tcp_ranges(_fields(sout).get("ports", ""))
    return {"state": "filtered", "zone": zone, "ranges": ranges}


def fix_command(zone: str) -> str:
    z = f" --zone={zone}" if zone else ""
    return (f"sudo firewall-cmd --permanent{z} --add-port={PORTS[0]}-{PORTS[-1]}/tcp && sudo firewall-cmd --reload")


def _candidates(fw: dict) -> tuple:
    """(ports to try in order, reachable: True / False / None for can't tell)"""
    if fw["state"] != "filtered":
        return list(PORTS), (True if fw["state"] in ("off", "open") else None)
    ranges = [(max(a, 1024), b) for a, b in fw["ranges"] if b >= 1024]
    inside = [p for p in PORTS if any(a <= p <= b for a, b in ranges)]
    if inside:
        return inside, True
    extra = []
    for a, b in sorted(ranges, key=lambda r: r[0] - r[1]):     # widest allowed range first
        # From the top of the range down: services usually sit at its start (KDE Connect uses 1716).
        extra += list(range(b, max(a, b - 40) - 1, -1))
    if extra:
        return extra[:80], True
    return list(PORTS), False


# ------------------------------------------------------------------ the page

class LanPage:
    """render(err_html) -> body html of the form; submit(form: dict[str, list[str]]) -> (ok, message),
    both called from the server thread."""

    def __init__(self, name: str, title: str, render, submit, ttl: int = 600, max_body: int = 8192):
        self.name, self.title, self.render, self.submit = name, title, render, submit
        self.ttl, self.max_body = ttl, max_body
        self.server = None
        self.token = ""
        self.url = ""
        self.started = 0.0
        self.received = False
        self.visited = False
        self.net = {}
        self.lock = threading.Lock()

    def start(self) -> dict:
        with self.lock:
            if self.server and time.time() - self.started < self.ttl - 30:
                return self.status()
            self._stop_locked()
            ip, iface = lan_address()
            if not ip:
                return {"ok": False, "error": "Not connected to Wi-Fi. Connect to the same network as your phone and try again."}
            fw = firewall(iface)
            ports, reachable = _candidates(fw)
            srv = None
            for port in ports:
                try:
                    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), self._handler())
                    break
                except OSError:
                    continue
            if srv is None:
                try:
                    srv = http.server.ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
                    reachable = True if fw["state"] in ("off", "open") else None
                except OSError as e:
                    return {"ok": False, "error": f"Couldn't open the sign-in page ({e.strerror or e})."}
            srv.daemon_threads = True
            srv.timeout = 1
            self.token = base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip("=")
            self.received = self.visited = False
            self.server = srv
            port = srv.server_address[1]
            self.url = f"http://{ip}:{port}/{self.token}"
            self.started = time.time()
            self.net = {"ip": ip, "iface": iface, "port": port, "firewall": fw["state"], "zone": fw.get("zone", ""),
                        "blocked": reachable is False, "fix": "" if reachable else fix_command(fw.get("zone", ""))}
            threading.Thread(target=self._serve, args=(srv,), daemon=True).start()
            return self.status()

    def _handler(self):
        lp = self

        class H(http.server.BaseHTTPRequestHandler):
            server_version = lp.name
            sys_version = ""

            def log_message(self, *a):
                pass

            def _send(self, code: int, body: str):
                data = page(lp.title, body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(data)

            def _mine(self) -> bool:
                return bool(lp.token) and urllib.parse.urlparse(self.path).path == f"/{lp.token}"

            def do_GET(self):
                if not self._mine():
                    self.send_error(404)
                    return
                lp.visited = True
                if lp.received:
                    self._send(200, '<p class="ok">Already signed in. You can close this page.</p>')
                    return
                self._send(200, lp.render(""))

            def do_POST(self):
                if not self._mine() or lp.received:
                    self.send_error(404)
                    return
                lp.visited = True
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = 0
                if n <= 0 or n > lp.max_body:
                    self.send_error(413)
                    return
                form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                try:
                    ok, msg = lp.submit(form)
                except Exception as e:  # never leave the phone on a dead connection
                    ok, msg = False, f"Something went wrong on the handheld ({e})."
                if ok:
                    lp.received = True
                    self._send(200, f'<p class="ok">{html.escape(msg)}</p><p>You can close this page.</p>')
                    threading.Thread(target=lp.stop, daemon=True).start()
                else:
                    self._send(200, lp.render(f'<p class="err">{html.escape(msg)}</p>'))

        return H

    def _serve(self, srv):
        try:
            while self.server is srv and time.time() - self.started < self.ttl:
                srv.handle_request()
        finally:
            with self.lock:
                if self.server is srv:
                    self._stop_locked()

    def status(self) -> dict:
        live = self.server is not None
        return {"ok": live, "url": self.url if live else "", "received": self.received, "visited": self.visited,
                "expires": int(self.started + self.ttl) if live else 0, **self.net}

    def _stop_locked(self):
        srv, self.server = self.server, None
        if srv:
            try:
                srv.server_close()
            except OSError:
                pass

    def stop(self):
        with self.lock:
            self._stop_locked()
