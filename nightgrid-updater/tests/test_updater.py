import hashlib, io, json, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from ngupdate import updater, net  # noqa: E402

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


def release(tag, draft=False, pre=False, assets=True, url_tag=None):
    t = url_tag or tag
    a = [{"name": "Nightgrid.zip", "browser_download_url": REPO + t + "/Nightgrid.zip"},
         {"name": "Nightgrid.zip.sha256", "browser_download_url": REPO + t + "/Nightgrid.zip.sha256"}] if assets else []
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "assets": a, "html_url": "", "body": ""}


class PickRelease(unittest.TestCase):
    def test_newest_stable_with_assets(self):
        rels = [release("nightgrid-theme-v0.2.0"), release("nightgrid-theme-v0.10.0"),
                release("nightgrid-theme-v0.11.0", pre=True), release("nightgrid-theme-v0.12.0", draft=True),
                release("nightgrid-theme-v0.13.0", assets=False), release("ally-tweaks-v9.0.0"),
                release("nightgrid-theme-vbad")]
        self.assertEqual(updater.pick_release(rels)["version"], "v0.10.0")

    def test_none(self):
        self.assertIsNone(updater.pick_release([release("other-v1.0.0")]))


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
        rel = updater.pick_release([release("nightgrid-theme-v0.3.0")])
        self.assertEqual(updater.download(rel), data)

    def test_bad_checksum(self):
        data = make_zip()
        self._serve(data, "0" * 64 + "  Nightgrid.zip\n")
        rel = updater.pick_release([release("nightgrid-theme-v0.3.0")])
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            updater.download(rel)

    def test_digest_disagrees(self):
        data = make_zip()
        self._serve(data, hashlib.sha256(data).hexdigest())
        rel = updater.pick_release([release("nightgrid-theme-v0.3.0")])
        rel["zip"]["digest"] = "sha256:" + "1" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            updater.download(rel)

    def test_asset_from_other_repo_rejected(self):
        rel = updater.pick_release([release("nightgrid-theme-v0.3.0")])
        rel["zip"]["browser_download_url"] = "https://github.com/evil/repo/releases/download/x/Nightgrid.zip"
        rel["sha"]["browser_download_url"] = rel["zip"]["browser_download_url"] + ".sha256"
        with self.assertRaises(ValueError):
            updater.download(rel)

    def test_url_guard(self):
        for bad in ["http://github.com/x", "https://example.com/x", "file:///etc/passwd"]:
            with self.assertRaises(ValueError):
                net.check_url(bad)
        net.check_url("https://release-assets.githubusercontent.com/x")


class VerifyZip(unittest.TestCase):
    def test_rejects_traversal_and_foreign_paths(self):
        for name in ["../evil", "/abs/file", "Other/theme.json", "Nightgrid/../../x", "Nightgrid\\x"]:
            files = {"Nightgrid/theme.json": json.dumps({"name": "Nightgrid"}), name: "x"}
            with self.assertRaises(ValueError, msg=name):
                updater.verify_zip(make_zip(files))

    def test_rejects_symlink(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("Nightgrid/theme.json", json.dumps({"name": "Nightgrid"}))
            i = zipfile.ZipInfo("Nightgrid/link")
            i.external_attr = (0o120777 << 16)
            z.writestr(i, "/etc/passwd")
        with self.assertRaisesRegex(ValueError, "link"):
            updater.verify_zip(b.getvalue())

    def test_rejects_wrong_theme_and_manifest(self):
        with self.assertRaises(ValueError):
            updater.verify_zip(make_zip(name="Other"))
        files = {"Nightgrid/theme.json": json.dumps({"name": "Nightgrid", "manifest_version": 99})}
        with self.assertRaisesRegex(ValueError, "newer CSS Loader"):
            updater.verify_zip(make_zip(files))


class Install(unittest.TestCase):
    def test_fresh_install_and_update_keeps_options(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "homebrew", "data", "Nightgrid Updater")
            self.assertEqual(updater.install_zip(make_zip(version="v0.2.0"), home, work), "v0.2.0")
            tdir = os.path.join(home, "homebrew", "themes", "Nightgrid")
            with open(os.path.join(tdir, "config_USER.json"), "w") as f:
                f.write('{"active": true, "Palette": "Ice"}')
            with open(os.path.join(tdir, "css", "stale.css"), "w") as f:
                f.write("x")
            self.assertEqual(updater.install_zip(make_zip(version="v0.3.0"), home, work), "v0.3.0")
            self.assertEqual(updater.installed_version(home), "v0.3.0")
            with open(os.path.join(tdir, "config_USER.json")) as f:
                self.assertIn("Ice", f.read())
            self.assertFalse(os.path.exists(os.path.join(tdir, "css", "stale.css")))
            self.assertEqual(os.listdir(work), [])          # staging + backup cleaned up
            self.assertEqual(os.listdir(os.path.dirname(tdir)), ["Nightgrid"])

    def test_bad_zip_leaves_install_untouched(self):
        with tempfile.TemporaryDirectory() as home:
            work = os.path.join(home, "w")
            updater.install_zip(make_zip(version="v0.2.0"), home, work)
            with self.assertRaises(ValueError):
                updater.install_zip(make_zip({"../x": "y"}), home, work)
            self.assertEqual(updater.installed_version(home), "v0.2.0")


if __name__ == "__main__":
    unittest.main()
