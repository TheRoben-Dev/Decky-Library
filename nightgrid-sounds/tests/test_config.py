import os, sys, tempfile, types, unittest
stub = types.ModuleType("decky")
stub.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp()
sys.modules["decky"] = stub
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import main  # noqa: E402


class Config(unittest.TestCase):
    def test_defaults_for_junk(self):
        self.assertEqual(main.clean(None), main.DEFAULTS)
        self.assertEqual(main.clean({"pack": "nope", "volume": "x", "enabled": 1}), main.DEFAULTS)

    def test_clamps_and_filters(self):
        c = main.clean({"pack": "pulse", "volume": 3, "enabled": False,
                        "cats": {"nav": "off", "select": "steam", "launch": "pack", "bogus": "off", "tab": "loud"}})
        self.assertEqual(c, {"enabled": False, "pack": "pulse", "volume": 1.0, "cats": {"nav": "off", "select": "steam"}})

    def test_roundtrip(self):
        saved = main.save({"pack": "glass", "volume": 0.355})
        self.assertEqual(saved["volume"], 0.35)
        self.assertEqual(main.load(), saved)


if __name__ == "__main__":
    unittest.main()
