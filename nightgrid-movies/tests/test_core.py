import os, random, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from ngmovies import core  # noqa: E402

CAT = '''{"boot": [{"id": "a", "name": "A", "file": "a.webm"}, {"id": "b", "name": "B", "file": "b.webm"},
                   {"id": "gone", "name": "Gone", "file": "missing.webm"}],
          "suspend": [{"id": "s", "name": "S", "file": "s.webm"}]}'''


class Core(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        r = self.t.name
        self.mov, self.ovr = os.path.join(r, "movies"), os.path.join(r, "home/.steam/root/config/uioverrides/movies")
        os.makedirs(self.mov)
        for n, body in (("a.webm", b"AAA"), ("b.webm", b"BBB"), ("s.webm", b"SSS")):
            open(os.path.join(self.mov, n), "wb").write(body)
        open(os.path.join(self.mov, "movies.json"), "w").write(CAT)
        self.store = core.Store(os.path.join(r, "settings/settings.json"))

    def tearDown(self):
        self.t.cleanup()

    def read(self, n):
        return open(os.path.join(self.ovr, n), "rb").read()

    def test_catalog_skips_missing_files(self):
        self.assertEqual([m["id"] for m in core.load_catalog(self.mov)["boot"]], ["a", "b"])

    def test_apply_and_switch(self):
        st = core.apply("boot", "a", self.mov, self.ovr, self.store)
        self.assertEqual(self.read("deck_startup.webm"), b"AAA")
        self.assertEqual((st["boot"], st["states"]["boot"]), ("a", "ours"))
        core.apply("boot", "b", self.mov, self.ovr, self.store)
        self.assertEqual(self.read("deck_startup.webm"), b"BBB")
        self.assertFalse(os.path.exists(os.path.join(self.ovr, "deck_startup.webm" + core.BACKUP_SUFFIX)))

    def test_suspend_writes_both(self):
        core.apply("suspend", "s", self.mov, self.ovr, self.store)
        self.assertEqual(self.read("steam_os_suspend.webm"), b"SSS")
        self.assertEqual(self.read("steam_os_suspend_from_throbber.webm"), b"SSS")

    def test_foreign_file_is_kept_and_restored(self):
        os.makedirs(self.ovr)
        open(os.path.join(self.ovr, "deck_startup.webm"), "wb").write(b"MINE")
        core.apply("boot", "a", self.mov, self.ovr, self.store)
        self.assertEqual(self.read("deck_startup.webm" + core.BACKUP_SUFFIX), b"MINE")
        core.apply("boot", "", self.mov, self.ovr, self.store)
        self.assertEqual(self.read("deck_startup.webm"), b"MINE")
        self.assertFalse(os.path.exists(os.path.join(self.ovr, "deck_startup.webm" + core.BACKUP_SUFFIX)))

    def test_foreign_symlink_moved_aside(self):
        os.makedirs(self.ovr)
        os.symlink("/nowhere.webm", os.path.join(self.ovr, "deck_startup.webm"))
        core.apply("boot", "a", self.mov, self.ovr, self.store)
        self.assertTrue(os.path.islink(os.path.join(self.ovr, "deck_startup.webm" + core.BACKUP_SUFFIX)))
        core.restore_all(self.mov, self.ovr, self.store)
        self.assertTrue(os.path.islink(os.path.join(self.ovr, "deck_startup.webm")))

    def test_replaced_behind_our_back(self):
        core.apply("boot", "a", self.mov, self.ovr, self.store)
        open(os.path.join(self.ovr, "deck_startup.webm"), "wb").write(b"OTHER")
        st = core.status(self.mov, self.ovr, core.Store(self.store.path))
        self.assertEqual((st["boot"], st["states"]["boot"]), ("", "other"))
        core.apply("boot", "", self.mov, self.ovr, self.store)          # turning off never deletes theirs
        self.assertEqual(self.read("deck_startup.webm"), b"OTHER")

    def test_shuffle_picks_another(self):
        core.apply("boot", "a", self.mov, self.ovr, self.store)
        self.assertEqual(core.shuffle_boot(self.mov, self.ovr, self.store, random.Random(1)), "b")
        self.assertEqual(self.read("deck_startup.webm"), b"BBB")

    def test_saver_settings(self):
        self.assertEqual(self.store.data["saver"], {"enabled": True, "minutes": 5, "style": "random"})
        self.assertEqual(core.clean_saver({"enabled": False, "minutes": 7, "style": "evil"}),
                         {"enabled": False, "minutes": 5, "style": "random"})
        self.store.data["saver"] = core.clean_saver({"minutes": 10, "style": "clock"})
        self.store.save()
        self.assertEqual(core.Store(self.store.path).data["saver"]["style"], "clock")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            core.apply("boot", "nope", self.mov, self.ovr, self.store)
        with self.assertRaises(ValueError):
            core.apply("idle", "a", self.mov, self.ovr, self.store)


if __name__ == "__main__":
    unittest.main()
