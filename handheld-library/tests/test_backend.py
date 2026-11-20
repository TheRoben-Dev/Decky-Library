import asyncio
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))

from hhlib import protondb, settings  # noqa: E402


class SettingsTest(unittest.TestCase):
    def test_defaults_and_coercion(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s", "settings.json")
            self.assertEqual(settings.load(p), settings.DEFAULTS)
            s = settings.save(p, {"deckMin": "bogus", "protonDB": "gold", "steamOS": "yes",
                                  "collectionName": "  ", "unknown": 1})
            self.assertEqual(s["deckMin"], "playable")
            self.assertEqual(s["protonDB"], "gold")
            self.assertIs(s["steamOS"], True)          # wrong type ignored
            self.assertEqual(s["collectionName"], "Handheld Ready")
            self.assertNotIn("unknown", s)
            s = settings.save(p, {"hiddenQamTabs": [3, "999", "48151", 3, {"x": 1}]})
            self.assertEqual(s["hiddenQamTabs"], ["3", "48151"])
            self.assertEqual(settings.load(p), s)


class ProtonDBTest(unittest.TestCase):
    def test_rank(self):
        self.assertGreater(protondb.tier_rank("Platinum"), protondb.tier_rank("gold"))
        self.assertEqual(protondb.tier_rank("pending"), -1)
        self.assertEqual(protondb.tier_rank("none"), -1)

    def test_lookup_uses_cache_and_survives_errors(self):
        with tempfile.TemporaryDirectory() as d:
            cache = protondb.Cache(os.path.join(d, "c.json"))
            cache.put(10, "gold", time.time())
            calls = []

            def fake(appid):
                calls.append(appid)
                if appid == 30:
                    raise OSError("offline")
                return "platinum"

            with mock.patch.object(protondb, "_fetch_one", fake):
                out = asyncio.run(protondb.lookup(cache, [10, 20, 30, 20]))
            self.assertEqual(out, {10: "gold", 20: "platinum"})
            self.assertEqual(sorted(calls), [20, 30])
            again = protondb.Cache(os.path.join(d, "c.json"))
            self.assertEqual(again.get(20, time.time()), "platinum")
            self.assertIsNone(again.get(20, time.time() + 8 * 86400))   # expired


if __name__ == "__main__":
    unittest.main()
