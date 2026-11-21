import json, os, sys, tempfile, unittest, urllib.parse
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from gridart import sgdb  # noqa: E402
from gridart.store import Store  # noqa: E402


class Query(unittest.TestCase):
    def q(self, *a, **k):
        return dict(urllib.parse.parse_qsl(sgdb.build_query(*a, **k)))

    def test_static_grids_filter_shape_and_mimes(self):
        q = self.q("grids", dimensions=sgdb.DIMENSIONS["capsule"], styles=["material", "bogus"])
        self.assertEqual(q["types"], "static")
        self.assertEqual(q["mimes"], "image/png,image/jpeg")
        self.assertEqual(q["dimensions"], "600x900,342x482,660x930")
        self.assertEqual(q["styles"], "material")
        self.assertEqual(q["nsfw"], "false")

    def test_animated_only_apng(self):
        q = self.q("heroes", animated=True, dimensions="ignored")
        self.assertEqual((q["types"], q["mimes"]), ("animated", "image/png"))
        self.assertNotIn("dimensions", q)

    def test_logos_png_and_opt_ins(self):
        q = self.q("logos", nsfw=True, humor=False, epilepsy=True, page=2)
        self.assertEqual(q["mimes"], "image/png")
        self.assertEqual((q["nsfw"], q["humor"], q["epilepsy"], q["page"]), ("any", "false", "any", "2"))


class Hosts(unittest.TestCase):
    def test_hosts(self):
        self.assertTrue(sgdb._host_ok("https://www.steamgriddb.com/api/v2/x", True))
        self.assertFalse(sgdb._host_ok("https://cdn2.steamgriddb.com/x", True))
        self.assertTrue(sgdb._host_ok("https://cdn2.steamgriddb.com/grid/a.png", False))
        self.assertFalse(sgdb._host_ok("http://cdn2.steamgriddb.com/grid/a.png", False))
        self.assertFalse(sgdb._host_ok("https://evilsteamgriddb.com/a.png", False))
        self.assertFalse(sgdb._host_ok("https://steamgriddb.com.evil.net/a.png", False))


class Images(unittest.TestCase):
    def test_magic(self):
        self.assertEqual(sgdb.image_type(b"\x89PNG\r\n\x1a\nrest"), "png")
        self.assertEqual(sgdb.image_type(b"\xff\xd8\xff\xe0"), "jpg")
        self.assertEqual(sgdb.image_type(b"RIFF....WEBP"), "")

    def test_download_rejects_webp(self):
        with mock.patch.object(sgdb, "_read", return_value=(b"RIFF....WEBP", "image/webp")):
            with self.assertRaises(sgdb.ApiError):
                sgdb.download("https://cdn2.steamgriddb.com/a.webp")


class Api(unittest.TestCase):
    def setUp(self):
        sgdb.clear_cache()

    def test_needs_key(self):
        with self.assertRaises(sgdb.ApiError) as cm:
            sgdb.api_get("/x", "")
        self.assertEqual(cm.exception.status, 401)

    def test_cache_and_slim(self):
        body = json.dumps({"success": True, "data": [{"id": 1, "url": "https://cdn2.steamgriddb.com/a.png",
                                                       "thumb": "t", "author": {"name": "me"}, "junk": 1}]}).encode()
        with mock.patch.object(sgdb, "_read", return_value=(body, "application/json")) as r:
            a = sgdb.assets("grids", "k" * 32, appid=220, query="page=0")
            sgdb.assets("grids", "k" * 32, appid=220, query="page=0")
        self.assertEqual(r.call_count, 1)
        self.assertEqual(a[0]["author"], "me")
        self.assertNotIn("junk", a[0])
        self.assertIn("/grids/steam/220?page=0", r.call_args[0][0])

    def test_shortcut_route_and_double_encoded_search(self):
        body = json.dumps({"success": True, "data": []}).encode()
        with mock.patch.object(sgdb, "_read", return_value=(body, "")) as r:
            sgdb.assets("logos", "k" * 32, game_id=5, query="")
            sgdb.search("AC/DC Live", "k" * 32)
        self.assertIn("/logos/game/5?", r.call_args_list[0][0][0])
        self.assertTrue(r.call_args_list[1][0][0].endswith("/search/autocomplete/AC%252FDC%2520Live"))


class Settings(unittest.TestCase):
    def test_key_never_public_and_file_private(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(os.path.join(d, "s", "settings.json"))
            s.data["key"] = "abcdefgh12345678"
            s.save()
            p = s.public()
            self.assertNotIn("key", p)
            self.assertEqual(p["keyHint"], "…5678")
            self.assertEqual(os.stat(s.path).st_mode & 0o777, 0o600)
            self.assertEqual(Store(s.path).data["key"], "abcdefgh12345678")

    def test_broken_file_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "settings.json")
            open(p, "w").write("{nope")
            self.assertEqual(Store(p).data["key"], "")


if __name__ == "__main__":
    unittest.main()
