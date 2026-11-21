import io, json, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from libhub import plugins  # noqa: E402


def pzip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return b.getvalue()


GOOD = {"Ally Tweaks/plugin.json": json.dumps({"name": "Ally Tweaks"}),
        "Ally Tweaks/package.json": json.dumps({"version": "0.2.0"}),
        "Ally Tweaks/main.py": "", "Ally Tweaks/dist/index.js": ""}


class InspectZip(unittest.TestCase):
    def test_good(self):
        self.assertEqual(plugins.inspect_zip(pzip(GOOD)), {"name": "Ally Tweaks", "version": "0.2.0"})

    def test_rejects(self):
        cases = [
            {**GOOD, "Other/x": ""},                                   # two top-level folders
            {**GOOD, "Ally Tweaks/../x": ""},
            {**GOOD, "/abs": ""},
            {k: v for k, v in GOOD.items() if not k.endswith("main.py")},
            {**GOOD, "Ally Tweaks/plugin.json": json.dumps({"name": "Something Else"})},
        ]
        for files in cases:
            with self.assertRaises(ValueError, msg=str(list(files))):
                plugins.inspect_zip(pzip(files))

    def test_rejects_symlink(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            for k, v in GOOD.items():
                z.writestr(k, v)
            i = zipfile.ZipInfo("Ally Tweaks/link")
            i.external_attr = (0o120777 << 16)
            z.writestr(i, "/etc/passwd")
        with self.assertRaisesRegex(ValueError, "link"):
            plugins.inspect_zip(b.getvalue())


class Installed(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as root:
            for d, name, ver in [("a", "CSS Loader", "2.1.3"), ("b", "Library Hub", "0.2.0"), ("c", None, None)]:
                os.makedirs(os.path.join(root, d))
                if name:
                    with open(os.path.join(root, d, "plugin.json"), "w") as f:
                        json.dump({"name": name}, f)
                if ver:
                    with open(os.path.join(root, d, "package.json"), "w") as f:
                        json.dump({"version": ver}, f)
            os.makedirs(os.path.join(root, "noversion"))
            with open(os.path.join(root, "noversion", "plugin.json"), "w") as f:
                json.dump({"name": "Old"}, f)
            self.assertEqual(plugins.installed(root), {"CSS Loader": "2.1.3", "Library Hub": "0.2.0", "Old": None})
        self.assertEqual(plugins.installed("/nonexistent"), {})


class Store(unittest.TestCase):
    def test_artifact(self):
        h = "a" * 64
        store = [{"name": "Other", "versions": [{"name": "1", "hash": "b" * 64}]},
                 {"name": "CSS Loader", "versions": [{"name": "2.1.3", "hash": h}, {"name": "2.1.2", "hash": "c" * 64}]}]
        a = plugins.store_artifact(store, "CSS Loader")
        self.assertEqual(a, {"artifact": plugins.STORE_CDN + h + ".zip", "hash": h, "version": "2.1.3", "name": "CSS Loader"})
        self.assertIsNone(plugins.store_artifact(store, "Missing"))
        bad = [{"name": "CSS Loader", "versions": [{"name": "x", "hash": "nothex"},
                                                   {"name": "y", "hash": h, "artifact": "http://insecure/x.zip"}]}]
        self.assertIsNone(plugins.store_artifact(bad, "CSS Loader"))


class Steam(unittest.TestCase):
    def test_libraries(self):
        with tempfile.TemporaryDirectory() as home:
            steam = os.path.join(home, ".local", "share", "Steam", "steamapps")
            sd = os.path.join(home, "sd")
            os.makedirs(steam)
            os.makedirs(os.path.join(sd, "steamapps"))
            with open(os.path.join(steam, "libraryfolders.vdf"), "w") as f:
                f.write('"libraryfolders"\n{\n "1"\n {\n  "path"  "%s"\n }\n}\n' % sd)
            self.assertFalse(plugins.steam_app_installed(home, 993090))
            open(os.path.join(sd, "steamapps", "appmanifest_993090.acf"), "w").close()
            self.assertTrue(plugins.steam_app_installed(home, 993090))


if __name__ == "__main__":
    unittest.main()
