"""lanlink: firewall-aware port choice and the one-time page (same test in each store plugin)."""
import glob, os, sys, unittest, urllib.error, urllib.parse, urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = glob.glob(os.path.join(HERE, "..", "py_modules", "*", "lanlink.py"))[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(PKG)))
lanlink = __import__(os.path.basename(os.path.dirname(PKG)) + ".lanlink", fromlist=["x"])

LIST_PUBLIC = """public (default, active)
  target: default
  interfaces: wlan0
  services: dhcpv6-client mdns ssh
  ports:
  rich rules:
"""
LIST_WORKSTATION = """FedoraWorkstation (active)
  target: default
  services: dhcpv6-client mdns samba-client ssh
  ports: 1025-65535/udp 1025-65535/tcp
"""
SERVICES = {"ssh": "ssh\n  ports: 22/tcp", "mdns": "mdns\n  ports: 5353/udp", "dhcpv6-client": "x\n  ports: 546/udp",
            "samba-client": "x\n  ports: 137/udp 138/udp", "kdeconnect": "kdeconnect\n  ports: 1714-1764/tcp 1714-1764/udp"}


def fake_fw(listing, state_rc=0):
    def run(args, timeout=4.0):
        a = args[1]
        if a == "--state":
            return state_rc, "running" if state_rc == 0 else "not running"
        if a.startswith("--get-zone-of-interface"):
            return 0, listing.split()[0]
        if a.startswith("--zone="):
            return 0, listing
        if a.startswith("--info-service="):
            return 0, SERVICES.get(a.split("=", 1)[1], "")
        return 1, ""
    return run


class Firewall(unittest.TestCase):
    def plan(self, listing, state_rc=0):
        with mock.patch.object(lanlink, "_which", return_value="/usr/bin/firewall-cmd"), \
             mock.patch.object(lanlink, "_run", side_effect=fake_fw(listing, state_rc)):
            return lanlink._candidates(lanlink.firewall("wlan0"))

    def test_workstation_zone_uses_fixed_port(self):
        ports, ok = self.plan(LIST_WORKSTATION)
        self.assertTrue(ok)
        self.assertEqual(ports[0], 47615)

    def test_public_zone_is_blocked(self):
        ports, ok = self.plan(LIST_PUBLIC)
        self.assertIs(ok, False)
        self.assertEqual(ports[0], 47615)

    def test_allowed_service_range_is_used(self):
        ports, ok = self.plan(LIST_PUBLIC.replace("mdns ssh", "kdeconnect mdns ssh"))
        self.assertTrue(ok)
        self.assertTrue(all(1714 <= p <= 1764 for p in ports))
        self.assertEqual(ports[0], 1764)

    def test_no_firewalld(self):
        with mock.patch.object(lanlink, "_which", return_value=""):
            self.assertEqual(lanlink._candidates(lanlink.firewall("wlan0")), (list(lanlink.PORTS), True))

    def test_firewalld_stopped(self):
        ports, ok = self.plan(LIST_PUBLIC, state_rc=252)
        self.assertTrue(ok)

    def test_fix_command(self):
        self.assertEqual(lanlink.fix_command("public"),
                         "sudo firewall-cmd --permanent --zone=public --add-port=47615-47619/tcp && sudo firewall-cmd --reload")

    def test_private_addresses(self):
        self.assertTrue(lanlink._private("192.168.1.20"))
        self.assertFalse(lanlink._private("100.101.1.2"))   # Tailscale
        self.assertFalse(lanlink._private("127.0.0.1"))
        self.assertTrue(lanlink._skip("tailscale0") and lanlink._skip("docker0") and not lanlink._skip("wlan0"))


class Page(unittest.TestCase):
    def test_one_time_page(self):
        got = []

        def submit(form):
            v = (form.get("v") or [""])[0]
            got.append(v)
            return (v == "good"), ("Signed in." if v == "good" else "Nope.")

        lp = lanlink.LanPage("t", "Test", lambda err: f'<form method="post"><input name="v"></form>{err}', submit, ttl=60)
        with mock.patch.object(lanlink, "lan_address", return_value=("127.0.0.1", "lo")), \
             mock.patch.object(lanlink, "firewall", return_value={"state": "off", "zone": ""}):
            st = lp.start()
        try:
            self.assertTrue(st["ok"])
            self.assertFalse(st["blocked"])
            url = st["url"]
            base = url.rsplit("/", 1)[0]
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/wrong", timeout=5)
            self.assertFalse(lp.status()["visited"])
            body = urllib.request.urlopen(url, timeout=5).read().decode()
            self.assertIn("Not secure", body)
            self.assertTrue(lp.status()["visited"])
            bad = urllib.request.urlopen(url, data=b"v=bad", timeout=5).read().decode()
            self.assertIn("Nope.", bad)
            ok = urllib.request.urlopen(url, data=urllib.parse.urlencode({"v": "good"}).encode(), timeout=5).read().decode()
            self.assertIn("Signed in.", ok)
            self.assertEqual(got, ["bad", "good"])
            self.assertTrue(lp.status()["received"])
        finally:
            lp.stop()
        self.assertFalse(lp.status()["ok"])

    def test_no_network(self):
        lp = lanlink.LanPage("t", "Test", lambda e: "", lambda f: (True, ""))
        with mock.patch.object(lanlink, "lan_address", return_value=("", "")):
            self.assertFalse(lp.start()["ok"])

    def test_only_bundled_modules(self):
        src = open(PKG).read()
        for m in ("import secrets", "import xml", "import uuid", "import tarfile", "html.parser"):
            self.assertNotIn(m, src)


if __name__ == "__main__":
    unittest.main()
