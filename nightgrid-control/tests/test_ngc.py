import json
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "py_modules"))

from ngc import agefile, profile, remote  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def fixture(name, mode="rb"):
    with open(os.path.join(FIX, name), mode) as f:
        return f.read()


class AgeTests(unittest.TestCase):
    """profile.age was written by the real `age -p` CLI (passphrase "nightgrid test")."""

    def test_decrypts_real_age_file(self):
        self.assertEqual(agefile.decrypt(fixture("profile.age"), "nightgrid test"), fixture("profile.json"))

    def test_pure_python_aead_matches(self):
        saved = agefile.aead_open
        agefile.aead_open = agefile._open_py
        try:
            self.assertEqual(agefile.decrypt(fixture("profile.age"), "nightgrid test"), fixture("profile.json"))
        finally:
            agefile.aead_open = saved

    def test_wrong_passphrase(self):
        with self.assertRaises(agefile.WrongPassphrase):
            agefile.decrypt(fixture("profile.age"), "nope nope")

    def test_tampered_payload(self):
        d = bytearray(fixture("profile.age"))
        d[-5] ^= 1
        with self.assertRaises(agefile.AgeError):
            agefile.decrypt(bytes(d), "nightgrid test")

    def test_not_age(self):
        with self.assertRaises(agefile.AgeError):
            agefile.decrypt(b"hello", "x")
        self.assertTrue(agefile.is_passphrase_file(fixture("profile.age")[:64]))

    def test_rfc8439_vectors(self):
        # RFC 8439 2.5.2 (Poly1305) and 2.4.2 (ChaCha20, first bytes).
        key = bytes.fromhex("85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b")
        self.assertEqual(agefile._poly1305(key, b"Cryptographic Forum Research Group").hex(),
                         "a8061dc1305136c6c22b8baf0c0127a9")
        k = bytes(range(32))
        nonce = bytes.fromhex("000000000000004a00000000")
        pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
              b"sunscreen would be it.")
        self.assertEqual(agefile._chacha20(k, 1, nonce, pt)[:16].hex(), "6e2e359a2568f98041ba0728dd0d6981")


class ProfileTests(unittest.TestCase):
    def test_export(self):
        p = profile.read_export(fixture("profile.age"), "nightgrid test")
        names = [h["name"] for h in p["hosts"]]
        self.assertEqual(names[0], "local")  # favorite first
        self.assertEqual(set(names), {"local", "nas-off", "laptop"})
        local = p["hosts"][0]
        self.assertEqual((local["port"], local["username"], local["group"]), (2222, "tester", "Rack"))
        self.assertEqual(p["secrets"], {"1": {"host-password": "pw-test-123"}})  # integration token dropped
        nas = next(h for h in p["hosts"] if h["name"] == "nas-off")
        self.assertEqual((nas["mac"], nas["wakeRelay"]), ("AA-BB-CC-DD-EE-FF", 1))

    def test_local_db(self):
        with tempfile.TemporaryDirectory() as home:
            d = os.path.join(home, ".local", "share", profile.APP_ID)
            os.makedirs(d)
            con = sqlite3.connect(os.path.join(d, "nightgrid.db"))
            con.executescript("""
              CREATE TABLE host_groups (id INTEGER PRIMARY KEY, name TEXT, color TEXT, icon TEXT, sort_order INT, created_at INT);
              CREATE TABLE hosts (id INTEGER PRIMARY KEY, name TEXT, hostname TEXT, port INT, username TEXT, group_id INT,
                favorite INT, sort_order INT, auth_method TEXT, ssh_alias TEXT, role TEXT, mac_address TEXT);
              INSERT INTO host_groups VALUES (1, 'Lab', NULL, NULL, 0, 0);
              INSERT INTO hosts VALUES (5, 'pve', '10.0.0.2', 22, 'root', 1, 0, 0, 'agent', NULL, 'server', NULL);
            """)
            con.commit()
            con.close()
            env = os.environ.pop("XDG_DATA_HOME", None)
            try:
                r = profile.read_local(home)
            finally:
                if env is not None:
                    os.environ["XDG_DATA_HOME"] = env
            self.assertEqual(r["hosts"][0]["name"], "pve")
            self.assertEqual(r["hosts"][0]["group"], "Lab")
            self.assertEqual(r["secrets"], {})

    def test_find_exports_and_store(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Downloads", "sub"))
            with open(os.path.join(home, "Downloads", "sub", "nightgrid-backup.age"), "wb") as f:
                f.write(fixture("profile.age"))
            with open(os.path.join(home, "Downloads", "other.age"), "wb") as f:
                f.write(b"age-encryption.org/v1\n-> X25519 abc\n")  # not passphrase-encrypted
            found = profile.find_exports(home, "nobody")
            self.assertEqual([x["name"] for x in found], ["nightgrid-backup.age"])
            st = profile.Store(os.path.join(home, "settings dir"))
            st.save_export(found[0]["path"], profile.read_export(fixture("profile.age"), "nightgrid test"))
            self.assertEqual(oct(os.stat(st.path).st_mode & 0o777), "0o600")
            self.assertEqual(len(st.load()["hosts"]), 3)
            self.assertEqual(st.set_prefs({"interval": 30, "showClients": 1}), {"interval": 30, "showClients": True})
            self.assertEqual(st.set_prefs({"interval": 7})["interval"], 30)
            st.forget()
            self.assertIsNone(st.load())


class RemoteTests(unittest.TestCase):
    def test_parse_status(self):
        out = ("up=93784.12 1000.0\nc1=cpu  100 0 100 800 0 0 0 0 0 0\nc2=cpu  150 0 150 900 0 0 0 0 0 0\n"
               "mem=16000000 4000000\ndisk=91 /srv\ntemp=54000\nload=0.42\n")
        m = remote.parse_status(out.replace("up=93784.12 1000.0", "up=93784.12"))
        self.assertEqual(m["cpu"], 50.0)
        self.assertEqual(m["mem"], 75.0)
        self.assertEqual((m["disk"], m["mount"]), (91.0, "/srv"))
        self.assertEqual((m["temp"], m["load"], m["uptime"]), (54.0, 0.42, 93784.12))
        w = remote.parse_status("up=60\nmem=8000000 2000000\ncpu=12\ndisk=40 C:\n")
        self.assertEqual((w["cpu"], w["disk"], w["mount"]), (12.0, 40.0, "C:"))

    def test_window(self):
        import time
        base = time.mktime((2026, 11, 21, 23, 30, 0, 0, 0, -1))
        self.assertTrue(remote.in_window("23:00-07:00", base))
        self.assertFalse(remote.in_window("08:00-17:00", base))
        self.assertFalse(remote.in_window("garbage", base))

    def test_jump_and_classify(self):
        hosts = [{"name": "bastion", "alias": None, "hostname": "1.2.3.4", "port": 2200, "username": "me"}]
        self.assertEqual(remote.resolve_jump("bastion, other@x", hosts), "me@1.2.3.4:2200,other@x")
        self.assertEqual(remote.classify(255, "Permission denied (publickey)."), "auth")
        self.assertEqual(remote.classify(255, "Host key verification failed."), "hostkey")
        self.assertEqual(remote.classify(255, "Connection timed out"), "offline")

    def test_wol(self):
        mac = remote.parse_mac("aa-bb-cc-01-02-03")
        p = remote.magic_packet(mac)
        self.assertEqual(len(p), 102)
        self.assertEqual(p[:6], b"\xff" * 6)
        self.assertEqual(remote._directed_broadcast("192.168.1.20"), "192.168.1.255")
        self.assertIsNone(remote._directed_broadcast("nas.lan"))
        with self.assertRaises(ValueError):
            remote.parse_mac("aa:bb")

    def test_build(self):
        with tempfile.TemporaryDirectory() as home:
            ctx = remote.Ctx(home, os.path.join(home, "set tings"), os.path.join(home, "ng"))
            h = {"id": 1, "name": "n", "hostname": "10.0.0.5", "port": 2222, "username": "u",
                 "identity": "C:\\Users\\me\\.ssh\\id_ed25519", "proxyJump": None, "alias": None, "tailnet": "100.1.2.3"}
            argv, env = remote.build(ctx, h, [h], {}, "true")
            self.assertIn("BatchMode=yes", argv)
            self.assertEqual(argv[-2:], ["10.0.0.5", "exec sh -c true"])
            self.assertIn("2222", argv)
            self.assertTrue(any(a.startswith("UserKnownHostsFile=\"") and "set tings" in a for a in argv))
            argv, env = remote.build(ctx, h, [h], {"host-password": "pw"}, "true", use_tailnet=True)
            self.assertIn("BatchMode=no", argv)
            self.assertEqual(argv[-2], "100.1.2.3")
            self.assertEqual(env["NGC_PASS"], "pw")
            self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_sudo_wrap(self):
        self.assertIn("sudo -n --", remote.sudo_wrap("echo hi", False))
        self.assertIn("sudo -S -k -p ''", remote.sudo_wrap("echo hi", True))


if __name__ == "__main__":
    unittest.main()
