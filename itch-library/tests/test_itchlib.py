import io, json, os, stat, sys, tarfile, tempfile, threading, unittest, urllib.parse, urllib.request, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from itchlib import api, install  # noqa: E402
from itchlib.handoff import Handoff  # noqa: E402
from itchlib.store import Installed, Settings  # noqa: E402

ELF64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + (2).to_bytes(2, "little") + (0x3E).to_bytes(2, "little") + b"\x00" * 200
ELF_ARM = b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + (2).to_bytes(2, "little") + (0xB7).to_bytes(2, "little") + b"\x00" * 200
PE = b"MZ" + b"\x00" * 300


def up(id, traits, **kw):
    d = {"id": id, "filename": kw.pop("filename", f"g{id}.zip"), "size": 1000, "storage": "hosted", "type": "default",
         "traits": traits}
    d.update(kw)
    return api.upload_info(d)


class Api(unittest.TestCase):
    def test_game_info_traits(self):
        g = api.game_info({"id": 5, "title": "T", "traits": ["p_linux", "p_windows", "can_be_bought"],
                           "user": {"display_name": "Dev"}, "cover_url": "https://img.itch.zone/a.png"})
        self.assertEqual(g["platforms"], ["linux", "windows"])
        self.assertEqual((g["author"], g["still"]), ("Dev", "https://img.itch.zone/a.png"))

    def test_pick_prefers_native_full_game(self):
        ups = [up(1, ["p_windows"]), up(2, ["p_linux", "demo"]), up(3, ["p_linux"]), up(4, ["p_osx"]),
               up(5, ["p_linux"], type="soundtrack")]
        self.assertEqual(api.pick_upload(ups)["id"], 3)
        self.assertEqual(api.pick_upload(ups, "windows")["id"], 1)

    def test_pick_skips_arm_and_external(self):
        ups = [up(1, ["p_linux"], filename="game-arm64.zip"), up(2, ["p_linux"], filename="game-x64.tar.gz"),
               up(3, ["p_linux"], storage="external")]
        self.assertEqual(api.pick_upload(ups)["id"], 2)
        self.assertIsNone(api.pick_upload([up(9, ["p_osx"])]))

    def test_fingerprint(self):
        self.assertEqual(api.fingerprint(up(1, [], build_id=77)), "b77")
        self.assertEqual(api.fingerprint(up(1, [], filename="a.zip", size=5)), "fa.zip:5")


class Unpack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cancel = threading.Event()

    def zipfile(self, entries):
        p = os.path.join(self.tmp, "a.zip")
        with zipfile.ZipFile(p, "w") as z:
            for name, data, mode in entries:
                zi = zipfile.ZipInfo(name)
                zi.external_attr = (mode & 0xFFFF) << 16
                z.writestr(zi, data)
        return p

    def test_zip_keeps_exec_bit_and_blocks_traversal(self):
        src = self.zipfile([("Game/game.x86_64", ELF64, 0o100755), ("Game/data.pck", b"x", 0o100644),
                            ("../evil.txt", b"x", 0o100644), ("/abs.txt", b"x", 0o100644)])
        dest = os.path.join(self.tmp, "out")
        info = install.unpack(src, dest, "a.zip", self.cancel)
        self.assertEqual(info["kind"], "zip")
        exe = os.path.join(dest, "Game", "game.x86_64")
        self.assertTrue(os.stat(exe).st_mode & stat.S_IXUSR)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.txt")))
        self.assertEqual(install.file_list(dest), sorted([os.path.join("Game", "data.pck"), os.path.join("Game", "game.x86_64")]))

    def test_tar(self):
        p = os.path.join(self.tmp, "a.tar.gz")
        with tarfile.open(p, "w:gz") as t:
            ti = tarfile.TarInfo("run.sh"); ti.size = 9; ti.mode = 0o755
            t.addfile(ti, io.BytesIO(b"#!/bin/sh"))
            ti = tarfile.TarInfo("link"); ti.type = tarfile.SYMTYPE; ti.linkname = "../../etc/passwd"
            t.addfile(ti)
        dest = os.path.join(self.tmp, "out")
        install.unpack(p, dest, "a.tar.gz", self.cancel)
        self.assertTrue(os.path.isfile(os.path.join(dest, "run.sh")))
        self.assertFalse(os.path.lexists(os.path.join(dest, "link")))

    def test_single_exe_and_elf(self):
        p = os.path.join(self.tmp, "dl")
        with open(p, "wb") as f:
            f.write(PE)
        dest = os.path.join(self.tmp, "out")
        info = install.unpack(p, dest, "Cool Game.exe", self.cancel)
        self.assertEqual((info["kind"], info["installer"]), ("pe", ""))
        self.assertTrue(os.path.isfile(os.path.join(dest, "Cool Game.exe")))

    def test_mac_build_refused(self):
        p = os.path.join(self.tmp, "x.dmg")
        with open(p, "wb") as f:
            f.write(b"koly" * 10)
        with self.assertRaises(install.InstallError):
            install.unpack(p, os.path.join(self.tmp, "o"), "x.dmg", self.cancel)


class Scan(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def put(self, rel, data, mode=0o644):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        os.chmod(p, mode)

    def test_linux_game_beats_helpers_and_arm(self):
        self.put("Star Hop/StarHop.x86_64", ELF64 * 50, 0o755)
        self.put("Star Hop/chrome-sandbox", ELF64 * 80, 0o755)
        self.put("Star Hop/StarHop-arm64", ELF_ARM * 50, 0o755)
        self.put("Star Hop/libfoo.so", ELF64, 0o755)
        c = install.scan(self.root, "Star Hop", [])
        self.assertEqual(c[0]["path"], os.path.join("Star Hop", "StarHop.x86_64"))
        self.assertNotIn(os.path.join("Star Hop", "StarHop-arm64"), [x["path"] for x in c])
        self.assertNotIn(os.path.join("Star Hop", "libfoo.so"), [x["path"] for x in c])

    def test_windows_uninstaller_and_crash_handler_lose(self):
        self.put("Game.exe", PE * 100)
        self.put("unins000.exe", PE * 300)
        self.put("UnityCrashHandler64.exe", PE * 400)
        c = install.scan(self.root, "Some Title", [])
        self.assertEqual(c[0]["path"], "Game.exe")

    def test_manifest_and_targets_win(self):
        self.put("a.exe", PE)
        self.put("b.exe", PE * 100)
        self.assertEqual(install.scan(self.root, "", [{"path": "a.exe"}])[0]["path"], "a.exe")
        self.put(".itch.toml", b'[[actions]]\nname = "play"\npath = "a.exe"\nargs = ["--fullscreen"]\n')
        c = install.scan(self.root, "", [])
        self.assertEqual((c[0]["path"], c[0]["args"]), ("a.exe", "--fullscreen"))

    def test_prefer_kind(self):
        self.put("game.exe", PE * 10)
        self.put("game.x86_64", ELF64 * 10, 0o755)
        self.assertEqual(install.scan(self.root, "game", [], "windows")[0]["kind"], "windows")
        self.assertEqual(install.scan(self.root, "game", [], "linux")[0]["kind"], "linux")


class CarryOver(unittest.TestCase):
    def test_keeps_saves_not_old_files(self):
        old, new = tempfile.mkdtemp(), tempfile.mkdtemp()
        for rel in ("game.exe", "old_only.dll", "saves/slot1.sav"):
            os.makedirs(os.path.dirname(os.path.join(old, rel)) or old, exist_ok=True)
            open(os.path.join(old, rel), "w").write("old")
        open(os.path.join(new, "game.exe"), "w").write("new")
        install.carry_over(old, new, ["game.exe", "old_only.dll"])
        self.assertEqual(open(os.path.join(new, "game.exe")).read(), "new")
        self.assertTrue(os.path.isfile(os.path.join(new, "saves", "slot1.sav")))
        self.assertFalse(os.path.exists(os.path.join(new, "old_only.dll")))


class Stores(unittest.TestCase):
    def test_settings_hide_key(self):
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        s = Settings(p)
        s.data["key"] = "secret"
        s.save()
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")
        pub = Settings(p).public()
        self.assertTrue(pub["signedIn"])
        self.assertNotIn("key", pub)

    def test_installed(self):
        p = os.path.join(tempfile.mkdtemp(), "i.json")
        i = Installed(p)
        i.put(3, {"game_id": 3})
        self.assertEqual(Installed(p).get(3), {"game_id": 3})
        i.drop(3)
        self.assertIsNone(Installed(p).get(3))


class HandoffTest(unittest.TestCase):
    def test_round_trip(self):
        got = []
        h = Handoff(lambda k: (got.append(k) or k == "good", "Signed in as tester." if k == "good" else "bad key"))
        st = h.start()
        if not st["ok"]:
            self.skipTest(st.get("error"))
        u = urllib.parse.urlparse(st["url"])
        base = f"http://127.0.0.1:{u.port}"
        self.assertIn("Send to handheld", urllib.request.urlopen(base + u.path, timeout=5).read().decode())
        with self.assertRaises(Exception):
            urllib.request.urlopen(base + "/wrong", timeout=5)
        r = urllib.request.urlopen(base + u.path, data=b"key=nope", timeout=5).read().decode()
        self.assertIn("bad key", r)
        r = urllib.request.urlopen(base + u.path, data=b"key=good", timeout=5).read().decode()
        self.assertIn("Signed in as tester.", r)
        self.assertEqual(got, ["nope", "good"])
        h.stop()


if __name__ == "__main__":
    unittest.main()
