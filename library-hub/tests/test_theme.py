import hashlib, io, json, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from libhub import releases, theme, net  # noqa: E402

REPO = "https://github.com/TheRoben-Dev/Decky-Library/releases/download/"


def make_zip(files=None, name="Nightgrid", version="v0.3.0"):
    files = files if files is not None else {
        "Nightgrid/theme.json": json.dumps({"name": name, "version": version, "manifest_version": 9}),
        "Nightgrid/css/tokens.css": ":root{}",
    }
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return b.getvalue()


def release(tag, draft=False, pre=False, assets=True, url_tag=None, zipname="Nightgrid.zip", title=""):
    t = url_tag or tag
    a = [{"name": zipname, "browser_download_url": REPO + t + "/" + zipname},
         {"name": zipname + ".sha256", "browser_download_url": REPO + t + "/" + zipname + ".sha256"}] if assets else []
    return {"tag_name": tag, "name": title, "draft": draft, "prerelease": pre, "assets": a, "html_url": "", "body": ""}


class Catalog(unittest.TestCase):
    def test_newest_stable_per_id(self):
        rels = [release("nightgrid-theme-v0.2.0"), release("nightgrid-theme-v0.10.0", title="Version Ten"),
                release("nightgrid-theme-v0.11.0", pre=True), release("nightgrid-theme-v0.12.0", draft=True),
                release("nightgrid-theme-v0.13.0", assets=False), release("nightgrid-theme-vbad"),
                release("ally-tweaks-v0.1.0", zipname="Ally-Tweaks.zip", title="Ally Tweaks v0.1.0"),
                release("ally-tweaks-v0.2.0", zipname="Ally-Tweaks.zip", title="Ally Tweaks v0.2.0"),
                release("nightgrid-updater-v0.1.0", zipname="Nightgrid-Updater.zip", title="Nightgrid Updater v0.1.0"),
                release("library-hub-v0.2.0", zipname="Library-Hub.zip", title="Library Hub v0.2.0")]
        cat = releases.catalog(rels)
        self.assertEqual(sorted(cat), ["ally-tweaks", "library-hub", "nightgrid-theme"])  # retired updater hidden
        self.assertEqual(cat["nightgrid-theme"]["version"], "0.10.0")
        self.assertEqual(cat["nightgrid-theme"]["name"], "Nightgrid")        # hand-made title ignored
        self.assertEqual(cat["nightgrid-theme"]["kind"], "theme")
        self.assertEqual(cat["ally-tweaks"]["version"], "0.2.0")
        self.assertEqual(cat["ally-tweaks"]["name"], "Ally Tweaks")
        self.assertEqual(cat["ally-tweaks"]["kind"], "plugin")

    def test_order_independent(self):
        rels = [release("x-v1.0.0", zipname="X.zip", title="X v1.0.0"), release("x-v2.0.0", zipname="X.zip", title="X v2.0.0")]
        self.assertEqual(releases.catalog(rels)["x"]["version"], "2.0.0")
        self.assertEqual(releases.catalog(rels[::-1])["x"]["version"], "2.0.0")

    def test_two_zips_skipped(self):
        r = release("x-v1.0.0", zipname="X.zip")
        r["assets"] += [{"name": "Y.zip", "browser_download_url": REPO + "x-v1.0.0/Y.zip"},
                        {"name": "Y.zip.sha256", "browser_download_url": REPO + "x-v1.0.0/Y.zip.sha256"}]
        self.assertEqual(releases.catalog([r]), {})


class Download(unittest.TestCase):
    def setUp(self):
        self.orig = net.fetch

    def tearDown(self):
        net.fetch = self.orig

    def _serve(self, data, sha):
        def fetch(url, max_bytes, accept="*/*", timeout=30):
            return sha.encode() if url.endswith(".sha256") else data
        net.fetch = fetch

    def test_good_checksum(self):
        data = make_zip()
        self._serve(data, hashlib.sha256(data).hexdigest() + "  Nightgrid.zip\n")
        rel = releases.catalog([release("nightgrid-theme-v0.3.0")])["nightgrid-theme"]
        self.assertEqual(releases.download(rel), (data, hashlib.sha256(data).hexdigest()))

    def test_bad_checksum(self):
        data = make_zip()
        self._serve(data, "0" * 64 + "  Nightgrid.zip\n")
        rel = releases.catalog([release("nightgrid-theme-v0.3.0")])["nightgrid-theme"]
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            releases.download(rel)

    def test_digest_disagrees(self):
        data = make_zip()
        self._serve(data, hashlib.sha256(data).hexdigest())
        rel = releases.catalog([release("nightgrid-theme-v0.3.0")])["nightgrid-theme"]
        rel["zip"]["digest"] = "sha256:" + "1" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            releases.download(rel)

    def test_asset_from_other_repo_rejected(self):
        rel = releases.catalog([release("nightgrid-theme-v0.3.0")])["nightgrid-theme"]
        rel["zip"]["browser_download_url"] = "https://github.com/evil/repo/releases/download/x/Nightgrid.zip"
        rel["sha"]["browser_download_url"] = rel["zip"]["browser_download_url"] + ".sha256"
        with self.assertRaises(ValueError):
            releases.download(rel)

    def test_url_guard(self):
        for bad in ["http://github.com/x", "https://example.com/x", "file:///etc/passwd"]:
            with self.assertRaises(ValueError):
                net.check_url(bad)
        net.check_url("https://release-assets.githubusercontent.com/x")
        with self.assertRaises(ValueError):
            net.check_url("https://plugins.deckbrew.xyz/plugins")          # store host only when asked
        net.check_url("https://plugins.deckbrew.xyz/plugins", net.STORE_HOSTS)


class VerifyZip(unittest.TestCase):
    def test_rejects_traversal_and_foreign_paths(self):
        for name in ["../evil", "/abs/file", "Other/theme.json", "Nightgrid/../../x", "Nightgrid\\x"]:
            files = {"Nightgrid/theme.json": json.dumps({"name": "Nightgrid"}), name: "x"}
            with self.assertRaises(ValueError, msg=name):
                theme.verify_zip(make_zip(files))

    def test_rejects_symlink(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("Nightgrid/theme.json", json.dumps({"name": "Nightgrid"}))
            i = zipfile.ZipInfo("Nightgrid/link")
            i.external_attr = (0o120777 << 16)
            z.writestr(i, "/etc/passwd")
        with self.assertRaisesRegex(ValueError, "link"):
            theme.verify_zip(b.getvalue())

    def test_rejects_wrong_theme_and_manifest(self):
        with self.assertRaises(ValueError):
            theme.verify_zip(make_zip(name="Other"))
        files = {"Nightgrid/theme.json": json.dumps({"name": "Nightgrid", "manifest_version": 99})}
        with self.assertRaisesRegex(ValueError, "newer CSS Loader"):
            theme.verify_zip(make_zip(files))


class Install(unittest.TestCase):
    def test_fresh_install_and_update_keeps_options(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "homebrew", "data", "Library Hub")
            self.assertEqual(theme.install_zip(make_zip(version="v0.2.0"), home, work), "v0.2.0")
            tdir = os.path.join(home, "homebrew", "themes", "Nightgrid")
            with open(os.path.join(tdir, "config_USER.json"), "w") as f:
                f.write('{"active": true, "Palette": "Ice"}')
            with open(os.path.join(tdir, "css", "stale.css"), "w") as f:
                f.write("x")
            self.assertEqual(theme.install_zip(make_zip(version="v0.3.0"), home, work), "v0.3.0")
            self.assertEqual(theme.installed_version(home), "v0.3.0")
            with open(os.path.join(tdir, "config_USER.json")) as f:
                self.assertIn("Ice", f.read())
            self.assertFalse(os.path.exists(os.path.join(tdir, "css", "stale.css")))
            self.assertEqual(os.listdir(work), [])          # staging + backup cleaned up
            self.assertEqual(os.listdir(os.path.dirname(tdir)), ["Nightgrid"])

    def test_bad_zip_leaves_install_untouched(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "w")
            theme.install_zip(make_zip(version="v0.2.0"), home, work)
            with self.assertRaises(ValueError):
                theme.install_zip(make_zip({"../x": "y"}), home, work)
            self.assertEqual(theme.installed_version(home), "v0.2.0")

    def test_uninstall(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "w")
            self.assertFalse(theme.uninstall(home, work))
            theme.install_zip(make_zip(version="v0.2.0"), home, work)
            self.assertTrue(theme.uninstall(home, work))
            self.assertIsNone(theme.installed_version(home))
            self.assertEqual(os.listdir(work), [])


class Lowpoly(unittest.TestCase):
    def lp_zip(self, version="v0.1.0", folder="Lowpoly", name="Lowpoly"):
        return make_zip({f"{folder}/theme.json": json.dumps({"name": name, "version": version, "manifest_version": 9}),
                         f"{folder}/css/tokens.css": ":root{}"})

    def test_catalog_kind_and_name(self):
        cat = releases.catalog([release("lowpoly-theme-v0.1.0", zipname="Lowpoly.zip", title="Lowpoly theme v0.1.0"),
                                release("nightgrid-theme-v0.6.4")])
        self.assertEqual(cat["lowpoly-theme"]["kind"], "theme")
        self.assertEqual(cat["lowpoly-theme"]["name"], "Lowpoly")
        self.assertEqual(cat["nightgrid-theme"]["name"], "Nightgrid")

    def test_installs_beside_nightgrid(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "w")
            theme.install_zip(make_zip(version="v0.6.4"), home, work)
            self.assertEqual(theme.install_zip(self.lp_zip(), home, work, "Lowpoly"), "v0.1.0")
            self.assertEqual(theme.installed_version(home, "Lowpoly"), "v0.1.0")
            self.assertEqual(theme.installed_version(home), "v0.6.4")
            self.assertTrue(theme.uninstall(home, work, "Lowpoly"))
            self.assertIsNone(theme.installed_version(home, "Lowpoly"))
            self.assertEqual(theme.installed_version(home), "v0.6.4")

    def test_wrong_theme_rejected(self):
        with self.assertRaises(ValueError):
            theme.verify_zip(make_zip(), "Lowpoly")                     # a Nightgrid zip
        with self.assertRaises(ValueError):
            theme.verify_zip(self.lp_zip(name="Nightgrid"), "Lowpoly")  # mislabelled theme.json


if __name__ == "__main__":
    unittest.main()
