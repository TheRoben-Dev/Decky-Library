import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from sweep import core  # noqa: E402


def mk(path, size=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)


class Tree(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = self.t.name
        self.steam = os.path.join(self.home, ".local/share/Steam")
        self.sd = os.path.join(self.home, "sd")
        sa = os.path.join(self.steam, "steamapps")
        mk(os.path.join(sa, "appmanifest_100.acf"))
        mk(os.path.join(sa, "shadercache/100/a.bin"), 5000)       # installed
        mk(os.path.join(sa, "shadercache/200/a.bin"), 7000)       # removed -> orphan
        mk(os.path.join(sa, "shadercache/300/a.bin"), 100)        # on SD (listed in vdf) -> installed
        mk(os.path.join(sa, "shadercache/3000000000/a.bin"), 50)  # shortcut
        mk(os.path.join(sa, "compatdata/200/pfx/save.dat"), 900)  # removed game prefix
        mk(os.path.join(sa, "compatdata/0/x"), 10)                # protected
        mk(os.path.join(sa, "compatdata/3000000000/pfx/x"), 10)   # shortcut prefix: never
        mk(os.path.join(sa, "workshop/content/200/item/x"), 300)
        mk(os.path.join(sa, "shadercache/notanid/x"), 10)
        os.makedirs(os.path.join(self.sd, "steamapps"))
        self.vdf(present=True)

    def vdf(self, present):
        sd = self.sd if present else os.path.join(self.home, "gone")
        mk(os.path.join(self.steam, "steamapps/libraryfolders.vdf"))
        with open(os.path.join(self.steam, "steamapps/libraryfolders.vdf"), "w") as f:
            f.write('"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n  "apps"\n  {\n   "100" "1"\n  }\n }\n'
                    ' "1"\n {\n  "path" "%s"\n  "apps"\n  {\n   "300" "1"\n  }\n }\n}\n' % (self.steam, sd))

    def tearDown(self):
        self.t.cleanup()

    def by(self, r):
        return {(e["kind"], e["appid"]): e for e in r["entries"]}

    def test_scan_classifies(self):
        e = self.by(core.scan(self.home, known_shortcuts=[123]))
        self.assertFalse(e[("shadercache", 100)]["orphan"])
        self.assertTrue(e[("shadercache", 200)]["orphan"])
        self.assertFalse(e[("shadercache", 300)]["orphan"])
        self.assertTrue(e[("shadercache", 3000000000)]["orphan"])
        self.assertTrue(e[("compatdata", 200)]["orphan"])
        self.assertTrue(e[("workshop", 200)]["orphan"])
        self.assertNotIn(("compatdata", 0), e)
        self.assertNotIn(("compatdata", 3000000000), e)

    def test_shortcut_cache_not_orphan_without_list(self):
        e = self.by(core.scan(self.home))
        self.assertFalse(e[("shadercache", 3000000000)]["orphan"])

    def test_missing_library_blocks_prefix_cleanup(self):
        self.vdf(present=False)
        r = core.scan(self.home, known_shortcuts=[1])
        self.assertTrue(r["missing"])
        self.assertFalse(self.by(r)[("compatdata", 200)]["orphan"])
        self.assertTrue(self.by(r)[("shadercache", 200)]["orphan"])

    def test_nothing_installed_means_no_orphans(self):
        os.unlink(os.path.join(self.steam, "steamapps/appmanifest_100.acf"))
        os.unlink(os.path.join(self.steam, "steamapps/libraryfolders.vdf"))
        r = core.scan(self.home)
        self.assertFalse(r["trusted"])
        self.assertFalse(any(e["orphan"] for e in r["entries"] if not e["shortcut"]))

    def test_running_game_skipped(self):
        self.assertNotIn(("shadercache", 100), self.by(core.scan(self.home, running=100)))

    def test_delete_only_cache_dirs(self):
        sa = os.path.join(self.steam, "steamapps")
        bad = [os.path.join(sa, "shadercache"), sa, self.home, os.path.join(sa, "shadercache/notanid"),
               os.path.join(sa, "compatdata/0"), os.path.join(sa, "shadercache/100/../200")]
        r = core.delete(bad, self.home)
        self.assertEqual(r["deleted"], [])
        self.assertTrue(os.path.isdir(os.path.join(sa, "shadercache/200")))
        r = core.delete([os.path.join(sa, "shadercache/200")], self.home)
        self.assertEqual(len(r["deleted"]), 1)
        self.assertGreater(r["freed"], 0)
        self.assertFalse(os.path.exists(os.path.join(sa, "shadercache/200")))

    def test_delete_refuses_symlink_and_running(self):
        sa = os.path.join(self.steam, "steamapps")
        os.symlink(self.home, os.path.join(sa, "shadercache/555"))
        r = core.delete([os.path.join(sa, "shadercache/555"), os.path.join(sa, "shadercache/100")], self.home, running=100)
        self.assertEqual(r["deleted"], [])
        self.assertTrue(os.path.isdir(self.home))


if __name__ == "__main__":
    unittest.main()
