"""GOG client pieces and the Galaxy (content-system) downloader, with GOG faked out."""
import hashlib, io, os, sys, tempfile, threading, unittest, zlib
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))

from goglib import api, galaxy, install  # noqa: E402


class Codes(unittest.TestCase):
    def test_extract_code(self):
        url = "https://embed.gog.com/on_login_success?origin=client&code=AbC-123_xyzAbC-123_xyzAbC-123_xyz"
        self.assertEqual(api.extract_code(url), "AbC-123_xyzAbC-123_xyzAbC-123_xyz")
        self.assertEqual(api.extract_code("  embed.gog.com/on_login_success?code=Zz%2D" + "a" * 30 + "&x=1 "), "Zz-" + "a" * 30)
        self.assertEqual(api.extract_code("a" * 40), "a" * 40)
        self.assertEqual(api.extract_code("hello"), "")
        self.assertEqual(api.extract_code(""), "")

    def test_login_url(self):
        self.assertIn("client_id=46899977096215655", api.LOGIN_URL)
        self.assertIn("redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient", api.LOGIN_URL)

    def test_token_only_to_gog(self):
        self.assertTrue(api.gog_host("https://content-system.gog.com/x"))
        self.assertFalse(api.gog_host("https://gog.com.evil.net/x"))
        self.assertFalse(api.gog_host("http://api.gog.com/x"))
        self.assertFalse(api.gog_host("https://gog-cdn.akamaized.net/x"))


class Parsing(unittest.TestCase):
    def test_catalog_item(self):
        p = {"id": "1207658787", "slug": "heroes_of_might_and_magic_3_complete_edition", "title": "Heroes 3",
             "productType": "game", "operatingSystems": ["windows", "osx"],
             "coverHorizontal": "https://images.gog-statics.com/a.png", "coverVertical": "https://images.gog-statics.com/b.jpg",
             "price": {"final": "$4.99", "base": "$9.99", "discount": "-50%", "finalMoney": {"amount": "4.99", "currency": "USD"}},
             "storeLink": "https://www.gog.com/en/game/heroes", "features": [{"name": "Controller support", "slug": "controller_support"}],
             "developers": ["NWC"]}
        it = api.catalog_item(p)
        self.assertEqual(it["id"], 1207658787)
        self.assertEqual(it["platforms"], ["windows", "mac"])
        self.assertFalse(it["free"])
        self.assertEqual(it["sale"], "-50%")
        self.assertTrue(it["controller"])
        free = api.catalog_item({"id": "5", "title": "F", "price": {"final": "Free", "finalMoney": {"amount": "0.00"}, "discount": "0%"}})
        self.assertTrue(free["free"])
        self.assertEqual(free["sale"], "")
        self.assertEqual(free["url"], "")

    def test_catalog_query(self):
        seen = {}

        def fake(url, token="", timeout=30):
            seen["url"] = url
            return {"pages": 3, "productCount": 120, "products": [{"id": "1", "title": "A"}]}
        with mock.patch.object(api, "get_json", side_effect=fake):
            r = api.catalog(price="free", genre="rpg", controller="controller", query="witcher", page=2)
        self.assertIn("features=in:controller_support", seen["url"])
        self.assertIn("price=between:0,0", seen["url"])
        self.assertIn("genres=in:rpg", seen["url"])
        self.assertIn("query=like:witcher", seen["url"])
        self.assertIn("systems=in:linux,windows", seen["url"])
        self.assertTrue(r["more"])
        with mock.patch.object(api, "get_json", side_effect=fake):
            api.catalog(controller="")
        self.assertNotIn("features=", seen["url"])
        self.assertIn("order=desc:trending", seen["url"])

    def test_platforms_and_images(self):
        self.assertEqual(api.platforms_of({"Windows": True, "Linux": True, "Mac": False}), ["linux", "windows"])
        self.assertEqual(api._img("//images-1.gog-statics.com/abc", "_392.jpg"), "https://images-1.gog-statics.com/abc_392.jpg")

    def test_pick_installer(self):
        ins = [{"os": "windows", "language": "de", "files": [1]}, {"os": "windows", "language": "en", "files": [1]},
               {"os": "linux", "language": "en", "files": [1]}, {"os": "linux", "language": "fr", "files": []}]
        self.assertEqual(api.pick_installer(ins, "windows", "de-DE")["language"], "de")
        self.assertEqual(api.pick_installer(ins, "windows", "pl-PL")["language"], "en")
        self.assertEqual(api.pick_installer(ins, "linux", "fr-FR")["language"], "en")
        self.assertIsNone(api.pick_installer(ins, "mac"))

    def test_endpoint_url_and_paths(self):
        ep = {"url_format": "{base_url}/token=nva={expires_at}~dirs=4~token={token}{path}",
              "parameters": {"base_url": "https://cdn.example", "path": "/content-system/v2/store/1", "token": "T", "expires_at": 9}}
        self.assertEqual(api.endpoint_url(ep, "/ab/cd/abcdef"),
                         "https://cdn.example/token=nva=9~dirs=4~token=T/content-system/v2/store/1/ab/cd/abcdef")
        self.assertEqual(api.galaxy_path("abcdef0123"), "ab/cd/abcdef0123")
        self.assertEqual(api.pick_build([{"branch": "beta", "link": "x"}, {"branch": None, "link": "y"}])["link"], "y")


def chunk(data: bytes) -> dict:
    z = zlib.compress(data)
    return {"md5": hashlib.md5(data).hexdigest(), "zmd5": hashlib.md5(z).hexdigest(), "size": len(data), "zsize": len(z), "_z": z}


class Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {}


class Galaxy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = {}

    def plan(self, files):
        out = []
        for path, parts in files:
            cs = [chunk(p) for p in parts]
            for c in cs:
                self.store[c["zmd5"]] = c.pop("_z")
            out.append({"path": path, "product": "1", "chunks": cs, "size": sum(c["size"] for c in cs),
                        "sig": hashlib.md5(b"".join(parts)).hexdigest(), "exe": False})
        return {"generation": 2, "build_id": "b", "version": "1", "files": out, "dirs": ["Saves"], "links": [], "timestamp": ""}

    def run_plan(self, p, old):
        calls = []

        def open_url(url, token="", headers=None, timeout=30):
            h = url.rsplit("/", 1)[1]
            calls.append(h)
            return Resp(self.store[h])
        eps = [{"url_format": "{base}{path}", "parameters": {"base": "https://cdn.example", "path": "/store"}}]
        with mock.patch.object(api, "open_url", side_effect=open_url), mock.patch.object(api, "secure_link", return_value=eps):
            ex = galaxy.Executor(1, p, self.dir, lambda: "tok", lambda d, t: None, threading.Event())
            receipt = ex.run(old, install.free_bytes)
        return receipt, calls

    def test_install_resume_update(self):
        p1 = self.plan([("Game.exe", [b"A" * 1000, b"B" * 500]), ("data/Level1.pak", [b"L1"]), ("data/old.pak", [b"old"])])
        r1, calls = self.run_plan(p1, None)
        self.assertEqual(len(calls), 4)
        with open(os.path.join(self.dir, "Game.exe"), "rb") as f:
            self.assertEqual(f.read(), b"A" * 1000 + b"B" * 500)
        self.assertTrue(os.path.isdir(os.path.join(self.dir, "Saves")))
        # Running again (resume after an interruption) downloads nothing.
        _, calls = self.run_plan(p1, None)
        self.assertEqual(calls, [])
        # The game writes a save; the next build changes one file, drops one, adds one with mixed case.
        with open(os.path.join(self.dir, "Saves", "slot1.sav"), "w") as f:
            f.write("mine")
        p2 = self.plan([("Game.exe", [b"A" * 1000, b"B" * 500]), ("DATA/Level1.pak", [b"L1-v2"]), ("data/new.pak", [b"n"])])
        r2, calls = self.run_plan(p2, r1)
        self.assertEqual(len(calls), 2)
        with open(os.path.join(self.dir, "data", "Level1.pak"), "rb") as f:
            self.assertEqual(f.read(), b"L1-v2")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "old.pak")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "DATA")))
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "Saves", "slot1.sav")))
        self.assertIn("DATA/Level1.pak".replace("/", os.sep), r2)

    def test_damaged_chunk_fails(self):
        p = self.plan([("x.bin", [b"good"])])
        for k in self.store:
            self.store[k] = zlib.compress(b"evil")
        with mock.patch.object(galaxy.time, "sleep"):
            with self.assertRaises(galaxy.DownloadError):
                self.run_plan(p, None)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "x.bin")))

    def test_rejects_escaping_paths(self):
        self.assertEqual(galaxy._rel("..\\..\\etc\\passwd"), "")
        self.assertEqual(galaxy._rel("bin\\game.exe"), os.path.join("bin", "game.exe"))

    def test_v2_plan_filters(self):
        meta = {"version": 2, "installDirectory": "Game", "products": [{"productId": "1"}, {"productId": "2"}, {"productId": "3"}],
                "depots": [{"productId": "1", "languages": ["*"], "manifest": "m1"},
                           {"productId": "1", "languages": ["de-DE"], "manifest": "mde"},
                           {"productId": "1", "languages": ["en-US"], "manifest": "men", "osBitness": ["32"]},
                           {"productId": "2", "languages": ["*"], "manifest": "dlc_owned"},
                           {"productId": "3", "languages": ["*"], "manifest": "dlc_not_owned"}]}
        fetched = []

        def zjson(url, token=""):
            if url == "LINK":
                return meta
            fetched.append(url.rsplit("/", 1)[1])
            return {"depot": {"items": [{"type": "DepotFile", "path": f"f_{url[-3:]}", "chunks": [], "md5": "x"},
                                        {"type": "DepotFile", "path": "support.ico", "flags": ["support"], "chunks": []}]}}
        with mock.patch.object(api, "get_zjson", side_effect=zjson):
            p = galaxy.plan(1, {"generation": 2, "link": "LINK", "build_id": "7", "version_name": "1.2"}, "t", "en-US", {2})
        self.assertEqual(sorted(fetched), ["dlc_owned", "m1"])
        self.assertEqual(p["build_id"], "7")
        self.assertFalse(any("support" in f["path"] for f in p["files"]))


class PlayTask(unittest.TestCase):
    def test_goggame_info(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "Bin"))
        open(os.path.join(d, "Bin", "Game.exe"), "wb").close()
        with open(os.path.join(d, "goggame-42.info"), "w") as f:
            f.write('{"playTasks":[{"category":"tool","isPrimary":false,"path":"tool.exe","type":"FileTask"},'
                    '{"category":"game","isPrimary":true,"path":"bin\\\\game.exe","arguments":"-skipintro","workingDir":"bin","type":"FileTask"}]}')
        t = install.play_task(d, 42)
        self.assertEqual(t["exe"], os.path.join(d, "Bin", "Game.exe"))
        self.assertEqual(t["args"], "-skipintro")
        self.assertEqual(t["workdir"], os.path.join(d, "Bin"))


if __name__ == "__main__":
    unittest.main()
