import os, sys, unittest, urllib.error
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from libhub import releases  # noqa: E402


def rel(tag, title=""):
    name = tag.rsplit("-v", 1)[0]
    base = f"{releases.DOWNLOAD_PREFIX}{tag}/"
    return {"tag_name": tag, "name": title, "assets": [
        {"name": f"{name}.zip", "browser_download_url": base + f"{name}.zip"},
        {"name": f"{name}.zip.sha256", "browser_download_url": base + f"{name}.zip.sha256"}]}


class FetchCatalog(unittest.TestCase):
    def setUp(self):
        releases._cache.update(at=0.0, cat=None)

    def test_paginates_until_short_page(self):
        page1 = [rel(f"proton-picker-v0.0.{i}") for i in range(100)]
        page2 = [rel("handheld-library-v0.5.1", "Handheld Library v0.5.1")]
        with mock.patch.object(releases.net, "get_json", side_effect=[page1, page2]) as g:
            cat = releases.fetch_catalog()
        self.assertEqual(g.call_count, 2)
        self.assertEqual(cat["handheld-library"]["name"], "Handheld Library")
        self.assertEqual(cat["proton-picker"]["version"], "0.0.99")

    def test_cached_unless_forced(self):
        with mock.patch.object(releases.net, "get_json", return_value=[rel("ally-tweaks-v0.1.4")]) as g:
            releases.fetch_catalog()
            releases.fetch_catalog()
            self.assertEqual(g.call_count, 1)
            releases.fetch_catalog(force=True)
            self.assertEqual(g.call_count, 2)

    def test_rate_limit_message(self):
        err = urllib.error.HTTPError(releases.RELEASES_URL, 403, "rate limited", {}, None)
        with mock.patch.object(releases.net, "get_json", side_effect=err):
            with self.assertRaises(RuntimeError) as cm:
                releases.fetch_catalog()
        self.assertIn("hourly limit", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
