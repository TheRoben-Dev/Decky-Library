import os, sys, tempfile, types, unittest
stub = types.ModuleType("decky")
stub.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp()
stub.DECKY_PLUGIN_RUNTIME_DIR = tempfile.mkdtemp()
stub.DECKY_USER_HOME = tempfile.mkdtemp()
import logging  # noqa: E402
stub.logger = logging.getLogger("t")
sys.modules["decky"] = stub
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import main  # noqa: E402


class Config(unittest.TestCase):
    def test_defaults_for_junk(self):
        self.assertEqual(main.clean(None), main.DEFAULTS)
        self.assertEqual(main.clean({"pack": "nope", "volume": "x", "enabled": 1}), main.DEFAULTS)

    def test_clamps_and_filters(self):
        c = main.clean({"pack": "neon", "volume": 3, "enabled": False,
                        "cats": {"nav": "off", "select": "steam", "launch": "pack", "bogus": "off", "tab": "loud"}})
        self.assertEqual(c, {"enabled": False, "pack": "neon", "volume": 1.0, "cats": {"nav": "off", "select": "steam"}})

    def test_roundtrip(self):
        saved = main.save({"pack": "terminal", "volume": 0.355})
        self.assertEqual(saved["volume"], 0.35)
        self.assertEqual(main.load(), saved)


import asyncio, base64  # noqa: E402

WAV = base64.b64encode(b"RIFF\x00\x00\x00\x00WAVEfmt ").decode()


class Files(unittest.TestCase):
    def setUp(self):
        self.ui = os.path.join(stub.DECKY_USER_HOME, ".local/share/Steam/steamui")
        os.makedirs(self.ui, exist_ok=True)

    def test_prepare_links_steamui_and_store_roundtrip(self):
        P = main.Plugin()
        r = asyncio.run(P.prepare("nightgrid-80"))
        self.assertEqual(r, {"ok": True, "base": "/sounds_nightgrid/", "have": False})
        link = os.path.join(self.ui, "sounds_nightgrid")
        self.assertEqual(os.path.realpath(link), os.path.realpath(main.sounds_dir()))
        files = {c: WAV for c in main.CATS + ("silent",)}
        self.assertEqual(asyncio.run(P.store_sounds("nightgrid-80", files)), {"ok": True})
        self.assertTrue(asyncio.run(P.prepare("nightgrid-80"))["have"])
        # a new set replaces the old one
        asyncio.run(P.store_sounds("pulse-50", files))
        self.assertFalse(asyncio.run(P.prepare("nightgrid-80"))["have"])
        self.assertTrue(os.path.isfile(os.path.join(link, "pulse-50", "nav.wav")))

    def test_relinks_stale_link_but_never_replaces_real_folder(self):
        link = os.path.join(self.ui, "sounds_nightgrid")
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink("/nonexistent", link)
        self.assertTrue(asyncio.run(main.Plugin().prepare("x"))["ok"])
        os.unlink(link)
        os.mkdir(link)
        self.assertFalse(asyncio.run(main.Plugin().prepare("x"))["ok"])
        os.rmdir(link)

    def test_rejects_bad_input(self):
        P = main.Plugin()
        self.assertFalse(asyncio.run(P.store_sounds("../evil", {"nav": WAV}))["ok"])
        self.assertFalse(asyncio.run(P.store_sounds("k", {"../x": WAV}))["ok"])
        self.assertFalse(asyncio.run(P.store_sounds("k", {"nav": base64.b64encode(b"notwav").decode()}))["ok"])
        self.assertFalse(asyncio.run(P.prepare("../x"))["have"])


if __name__ == "__main__":
    unittest.main()
