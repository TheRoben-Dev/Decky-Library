"""Sign in from your phone: a one-time page on the local network.

The sign-in screen shows a QR code for http://<device-ip>:<port>/<token>. The phone opens it,
follows the Amazon sign-in link (made on the handheld, so the code it returns only works here),
signs in, and pastes the amazon.com address it lands on back into the page. Nothing is typed on
the handheld. The server exists only while the sign-in screen asks for it, answers only on that
random path, accepts one sign-in and shuts down after it (or after 15 minutes).
"""
import html
import http.server
import secrets
import socket
import threading
import time
import urllib.parse

TTL = 900
MAX_BODY = 16384

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Amazon Library sign-in</title><style>
:root{color-scheme:dark}body{margin:0;background:#07080B;color:#E6EDF3;font:15px/1.5 ui-monospace,'JetBrains Mono',monospace;
background-image:linear-gradient(#1F2633 1px,transparent 1px),linear-gradient(90deg,#1F2633 1px,transparent 1px);background-size:40px 40px}
main{max-width:520px;margin:0 auto;padding:28px 18px}h1{font-size:18px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 4px}
.tag{color:#00E5FF;border:1px solid #00E5FF;padding:1px 6px;font-size:11px;letter-spacing:.1em}
p,li{color:#8B98A9}ol{padding-left:20px}a{color:#00E5FF}
textarea,input{width:100%;box-sizing:border-box;background:#0D0F14;border:1px solid #1F2633;color:#E6EDF3;padding:12px;font:inherit;margin:8px 0}
textarea:focus,input:focus{outline:none;border-color:#FF2A6D}button{width:100%;padding:12px;background:#FF2A6D;color:#07080B;border:0;font:inherit;font-weight:700;
letter-spacing:.08em;text-transform:uppercase}.ok{color:#2BFF88}a.go{display:block;text-align:center;padding:12px;border:1px solid #00E5FF;text-decoration:none;margin:6px 0 14px}textarea{min-height:90px;resize:vertical}.err{color:#FF9F1C}</style></head><body><main>
<h1>Amazon Library</h1><span class="tag">SIGN IN</span>
%BODY%
</main></body></html>"""

FORM = """<ol><li>Open the Amazon sign-in in a <b>new tab</b> and sign in (2-step codes work as usual).</li>
<li>You end up on the amazon.com home page. Copy that page's <b>full address</b> from the address bar.</li>
<li>Come back to this tab, paste it below and send it to your handheld.</li></ol>
<a class="go" href="%LOGIN%" target="_blank" rel="noopener noreferrer">Open Amazon sign-in &#8599;</a>
<form method="post"><textarea name="key" autocomplete="off" autocapitalize="off" spellcheck="false"
placeholder="https://www.amazon.com/?openid.oa2.authorization_code=..." required></textarea>
<button type="submit">Send to handheld</button></form>
<p>If the Amazon Shopping app opens instead, long-press the button and pick <b>Open in browser</b>.</p><p>%ERR%</p>"""


def lan_ip() -> str:
    """The address other devices on the network reach this one at (no packets are sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))   # TEST-NET; connect() on UDP only picks a route
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


class Handoff:
    def __init__(self, on_key, login_url):
        """on_key(text) -> (ok, message), called from the server thread.
        login_url() -> the Amazon sign-in address for this device."""
        self.on_key = on_key
        self.login_url = login_url
        self.server = None
        self.thread = None
        self.token = ""
        self.url = ""
        self.started = 0.0
        self.received = False
        self.lock = threading.Lock()

    def start(self) -> dict:
        with self.lock:
            if self.server and time.time() - self.started < TTL - 30:
                return self.status()
            self._stop_locked()
            ip = lan_ip()
            if not ip or ip.startswith("127."):
                return {"ok": False, "error": "Not connected to a network"}
            self.token = secrets.token_urlsafe(12)
            self.received = False
            handoff = self

            class H(http.server.BaseHTTPRequestHandler):
                server_version = "amazon-library"
                sys_version = ""

                def log_message(self, *a):
                    pass

                def _send(self, code: int, body: str):
                    data = PAGE.replace("%BODY%", body).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.end_headers()
                    self.wfile.write(data)

                def _mine(self) -> bool:
                    return urllib.parse.urlparse(self.path).path == f"/{handoff.token}"

                def do_GET(self):
                    if not self._mine():
                        self.send_error(404)
                        return
                    if handoff.received:
                        self._send(200, '<p class="ok">Already signed in. You can close this page.</p>')
                        return
                    self._send(200, handoff._form(""))

                def do_POST(self):
                    if not self._mine() or handoff.received:
                        self.send_error(404)
                        return
                    n = int(self.headers.get("Content-Length") or 0)
                    if n <= 0 or n > MAX_BODY:
                        self.send_error(413)
                        return
                    form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                    key = (form.get("key") or [""])[0].strip()
                    ok, msg = handoff.on_key(key)
                    if ok:
                        handoff.received = True
                        self._send(200, f'<p class="ok">{html.escape(msg)}</p><p>You can close this page.</p>')
                        threading.Thread(target=handoff.stop, daemon=True).start()
                    else:
                        self._send(200, handoff._form(f'<span class="err">{html.escape(msg)}</span>'))

            try:
                srv = http.server.ThreadingHTTPServer(("0.0.0.0", 0), H)
            except OSError as e:
                return {"ok": False, "error": f"Couldn't open the sign-in page ({e})"}
            srv.daemon_threads = True
            srv.timeout = 1
            self.server = srv
            self.url = f"http://{ip}:{srv.server_address[1]}/{self.token}"
            self.started = time.time()
            self.thread = threading.Thread(target=self._serve, args=(srv,), daemon=True)
            self.thread.start()
            return self.status()

    def _form(self, err: str) -> str:
        return FORM.replace("%LOGIN%", html.escape(self.login_url(), quote=True)).replace("%ERR%", err)

    def _serve(self, srv):
        try:
            while self.server is srv and time.time() - self.started < TTL:
                srv.handle_request()
        finally:
            with self.lock:
                if self.server is srv:
                    self._stop_locked()

    def status(self) -> dict:
        live = self.server is not None
        return {"ok": live, "url": self.url if live else "", "received": self.received,
                "expires": int(self.started + TTL) if live else 0}

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
