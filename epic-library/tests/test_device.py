"""Epic device-code sign-in, with Epic's endpoints faked."""
import os, sys, time, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "py_modules"))
from epiclib import device  # noqa: E402


class Device(unittest.TestCase):
    def run_flow(self, poll_answers):
        calls = []
        answers = list(poll_answers)

        def call(method, path, auth, form=None, timeout=20):
            calls.append((method, path, (form or {}).get("grant_type")))
            if path == "token" and form["grant_type"] == "client_credentials":
                return 200, {"access_token": "cc"}
            if path == "deviceAuthorization":
                self.assertEqual(auth, "bearer cc")
                return 200, {"user_code": "ABCD1234", "device_code": "dc", "expires_in": 600, "interval": 0,
                             "verification_uri_complete": "https://www.epicgames.com/id/activate?userCode=ABCD1234"}
            if path == "token" and form["grant_type"] == "device_code":
                return answers.pop(0)
            if path == "exchange":
                return 200, {"code": "exch"}
            if path.startswith("sessions/kill/"):
                return 204, {}
            raise AssertionError(path)

        got = []
        d = device.DeviceLogin(lambda c: (got.append(c) or (True, "Signed in as Tester.")))
        with mock.patch.object(device, "_call", side_effect=call), mock.patch.object(device.time, "sleep"):
            st = d.start()
            self.assertIn(st["state"], ("waiting", "finishing", "done", "error"))  # sleep is mocked, the poll may already be done
            self.assertEqual(st["code"], "ABCD1234")
            self.assertTrue(st["url"].startswith("https://www.epicgames.com/"))
            for _ in range(200):
                if d.status()["state"] not in ("waiting", "finishing"):
                    break
                time.sleep(0.01)
        return d.status(), got, calls

    def test_approved(self):
        pending = (400, {"errorCode": "errors.com.epicgames.account.oauth.authorization_pending"})
        st, got, calls = self.run_flow([pending, pending, (200, {"access_token": "user"})])
        self.assertEqual(st["state"], "done")
        self.assertEqual(got, ["exch"])
        self.assertIn(("DELETE", "sessions/kill/user", None), calls)

    def test_declined(self):
        st, got, _ = self.run_flow([(400, {"errorCode": "errors.com.epicgames.account.oauth.authorization_declined",
                                           "errorMessage": "Declined"})])
        self.assertEqual(st["state"], "error")
        self.assertEqual(got, [])

    def test_unreachable(self):
        d = device.DeviceLogin(lambda c: (True, ""))
        with mock.patch.object(device, "_call", side_effect=device.DeviceError("Couldn't reach Epic (offline).")):
            st = d.start()
        self.assertEqual(st["state"], "error")
        self.assertIn("reach Epic", st["error"])


if __name__ == "__main__":
    unittest.main()
