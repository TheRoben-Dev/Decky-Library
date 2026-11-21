"""Epic sign-in by device code: the phone only ever visits epicgames.com (real HTTPS, no local page,
no firewall involved).

Flow (Epic's OAuth device authorization grant, as used by Epic's console clients):
  1. client_credentials token for a client that may use the device-code grant,
  2. POST deviceAuthorization -> user_code + verification_uri_complete (epicgames.com/activate),
  3. poll the token endpoint with the device_code until the user approves on their phone,
  4. trade that session for a one-time exchange code, which Legendary signs in with
     (`legendary auth --token`), so Legendary ends up with its own normal session,
  5. end the temporary session.
The temporary token never leaves this process and is not stored.
"""
import base64
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .net import context

HOST = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth"
# Epic's own Switch client: one of the public clients allowed to use the device-code grant.
CLIENT = ("98f7e42c2e3a4f86a74eb43fbb41ed39", "0a2449a2-001a-451e-afec-3e812901c4d7")
BASIC = "basic " + base64.b64encode(f"{CLIENT[0]}:{CLIENT[1]}".encode()).decode()
UA = "EpicLibrary-Decky"




class DeviceError(Exception):
    pass


def _call(method: str, path: str, auth: str, form: dict | None = None, timeout: int = 20) -> tuple:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(f"{HOST}/{path}", data=data, method=method,
                                 headers={"Authorization": auth, "User-Agent": UA, "Accept": "application/json",
                                          **({"Content-Type": "application/x-www-form-urlencoded"} if data is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context()) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise DeviceError(f"Couldn't reach Epic ({getattr(e, 'reason', e)}).")


class DeviceLogin:
    """start() -> {ok, code, url, expires}; the worker thread polls and calls on_exchange(code) ->
    (ok, message) once the phone approves. status() reports progress for the sign-in screen."""

    def __init__(self, on_exchange):
        self.on_exchange = on_exchange
        self.lock = threading.Lock()
        self.gen = 0
        self.info = {}

    def start(self) -> dict:
        with self.lock:
            if self.info.get("state") == "waiting" and time.time() < self.info.get("expires", 0) - 30:
                return self.status()
            self.gen += 1
            gen = self.gen
        try:
            st, tok = _call("POST", "token", BASIC, {"grant_type": "client_credentials"})
            if st != 200 or not tok.get("access_token"):
                raise DeviceError(f"Epic refused the sign-in request ({tok.get('errorMessage') or st}).")
            st, dev = _call("POST", "deviceAuthorization", f"bearer {tok['access_token']}", {"prompt": "login"})
            if st != 200 or not dev.get("device_code"):
                raise DeviceError(f"Epic didn't give a sign-in code ({dev.get('errorMessage') or st}).")
        except DeviceError as e:
            with self.lock:
                if gen == self.gen:
                    self.info = {"state": "error", "error": str(e)}
            return self.status()
        code = dev.get("user_code", "")
        url = dev.get("verification_uri_complete") or f"https://www.epicgames.com/id/activate?userCode={urllib.parse.quote(code)}"
        with self.lock:
            if gen != self.gen:
                return self.status()
            self.info = {"state": "waiting", "code": code, "url": url,
                         "expires": int(time.time() + int(dev.get("expires_in") or 600)), "error": ""}
        threading.Thread(target=self._poll, args=(gen, dev["device_code"], max(3, int(dev.get("interval") or 5))),
                         daemon=True).start()
        return self.status()

    def _set(self, gen: int, **kw):
        with self.lock:
            if gen == self.gen:
                self.info.update(kw)

    def _poll(self, gen: int, device_code: str, interval: int):
        expires = self.info.get("expires", time.time() + 600)
        fails = 0
        while gen == self.gen and time.time() < expires:
            time.sleep(interval)
            if gen != self.gen:
                return
            try:
                st, tok = _call("POST", "token", BASIC, {"grant_type": "device_code", "device_code": device_code})
                fails = 0
            except DeviceError:
                fails += 1
                if fails >= 5:
                    self._set(gen, state="error", error="Lost the connection to Epic. Check the handheld's Wi-Fi and try again.")
                    return
                continue
            if st == 200 and tok.get("access_token"):
                self._finish(gen, tok["access_token"])
                return
            err = str(tok.get("errorCode", ""))
            if err.endswith("authorization_pending"):
                continue
            if err.endswith("slow_down"):
                interval += 5
                continue
            # Declined, expired or anything else: tell the screen; it can ask for a new code.
            self._set(gen, state="error", error=tok.get("errorMessage") or "Epic cancelled the sign-in. Get a new code and try again.")
            return
        if gen == self.gen:
            self._set(gen, state="expired", error="The code expired. Get a new one.")

    def _finish(self, gen: int, access: str):
        self._set(gen, state="finishing")
        bearer = f"bearer {access}"
        try:
            st, ex = _call("GET", "exchange", bearer)
            if st != 200 or not ex.get("code"):
                raise DeviceError(f"Epic didn't finish the sign-in ({ex.get('errorMessage') or st}).")
            ok, msg = self.on_exchange(ex["code"])
        except DeviceError as e:
            ok, msg = False, str(e)
        finally:
            try:
                _call("DELETE", f"sessions/kill/{urllib.parse.quote(access)}", bearer, timeout=10)
            except DeviceError:
                pass
        self._set(gen, state="done" if ok else "error", error="" if ok else msg, message=msg if ok else "")

    def status(self) -> dict:
        with self.lock:
            i = dict(self.info)
        return {"ok": i.get("state") in ("waiting", "finishing", "done"), "state": i.get("state", "idle"),
                "code": i.get("code", ""), "url": i.get("url", ""), "expires": i.get("expires", 0),
                "error": i.get("error", ""), "message": i.get("message", "")}

    def stop(self):
        with self.lock:
            self.gen += 1
            if self.info.get("state") in ("waiting",):
                self.info = {}
