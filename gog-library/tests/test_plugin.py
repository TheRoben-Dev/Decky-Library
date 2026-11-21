"""Sign-in, install, update and uninstall through the Plugin class with GOG faked out."""
import asyncio, io, logging, os, sys, tempfile, types, unittest, zipfile
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "py_modules"))
sys.path.insert(0, os.path.join(HERE, ".."))

TMP = tempfile.mkdtemp()
decky = types.ModuleType("decky")
decky.DECKY_USER_HOME = os.path.join(TMP, "home")
decky.DECKY_PLUGIN_SETTINGS_DIR = os.path.join(TMP, "settings")
decky.DECKY_PLUGIN_RUNTIME_DIR = os.path.join(TMP, "runtime")
decky.logger = logging.getLogger("gog-test")
EVENTS = []


async def emit(event, *args):
    EVENTS.append((event, args))
decky.emit = emit
sys.modules["decky"] = decky
os.makedirs(decky.DECKY_USER_HOME, exist_ok=True)

import main  # noqa: E402
from goglib import api, galaxy, install  # noqa: E402


def mojo(files) -> bytes:
    """A fake GOG Linux installer: a shell script with a zip glued on the end."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data, mode in files:
            zi = zipfile.ZipInfo(name)
            zi.external_attr = mode << 16
            z.writestr(zi, data)
    return b"#!/bin/sh\n# MojoSetup\n" + b"x" * 5000 + b"\nexit 0\n" + b.getvalue()


def product(version, size, installers=("linux",)):
    return {"id": 42, "title": "Star Hop", "slug": "star_hop", "url": "https://www.gog.com/game/star_hop", "short": "Hop.",
            "background": "", "logo": "", "platforms": list(installers), "game_type": "game", "preorder": False, "dlcs": [],
            "installers": [{"id": f"installer_{o}_en", "os": o, "language": "en", "version": version, "size": size, "name": "Star Hop",
                            "files": [{"id": "en1installer0", "size": size, "downlink": f"https://api.gog.com/products/42/downlink/{o}"}]}
                           for o in installers]}


GAME = {"id": 42, "title": "Star Hop", "cover": "", "image": "", "url": "", "platforms": ["linux"], "category": "", "hidden": False}


class Flow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p = main.Plugin()
        self.p.settings.data["auth"] = {"access_token": "a", "refresh_token": "r", "expires": 9e12}
        self.p.settings.data["user"] = {"id": "1", "username": "me"}
        self.p.loop = asyncio.get_running_loop()

    async def wait_job(self):
        for _ in range(500):
            if not self.p.jobs and (not self.p.worker or self.p.worker.done()):
                return
            await asyncio.sleep(0.01)
        self.fail("job didn't finish")

    async def test_linux_install_update_uninstall(self):
        p = self.p
        state = {"ver": "1.0", "payload": mojo([("data/noarch/start.sh", b"#!/bin/sh\n", 0o100755),
                                                ("data/noarch/game/StarHop", b"v1", 0o100755),
                                                ("scripts/ignored", b"x", 0o100644)])}

        def fake_download(url, size, dest, progress, cancel, base=0):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(state["payload"])
            progress(base + len(state["payload"]))
            return dest
        with mock.patch.object(api, "library", return_value=[GAME]), mock.patch.object(api, "owned_ids", return_value=[42]), \
                mock.patch.object(api, "product", side_effect=lambda gid, tok="": product(state["ver"], len(state["payload"]))), \
                mock.patch.object(api, "downlink", return_value="https://cdn.example/star_hop_1_0.sh"), \
                mock.patch.object(install, "download", side_effect=fake_download):
            lib = await p.library(False)
            self.assertTrue(lib["ok"])
            self.assertEqual(lib["games"][0]["id"], 42)
            g = await p.game(42)
            self.assertTrue(g["owned"])
            self.assertEqual(g["options"][0]["kind"], "linux")
            await p.install(42, "")
            await self.wait_job()
            rec = p.installed.get(42)
            self.assertIsNotNone(rec, EVENTS[-2:])
            self.assertEqual(rec["method"], "linux")
            self.assertTrue(rec["exe"].endswith("start.sh"))
            self.assertTrue(os.access(rec["exe"], os.X_OK))
            self.assertFalse(os.path.exists(os.path.join(rec["dir"], "scripts")))
            self.assertFalse(os.listdir(os.path.join(rec["root"], ".downloads")))
            # The game writes a config into its folder; a new installer version comes out.
            with open(os.path.join(rec["dir"], "game", "settings.cfg"), "w") as f:
                f.write("mine")
            state["ver"] = "1.1"
            state["payload"] = mojo([("data/noarch/start.sh", b"#!/bin/sh\n", 0o100755), ("data/noarch/game/StarHop", b"v2", 0o100755)])
            up = await p.check_updates()
            self.assertEqual(up["updates"], 1)
            await p.install(42, "")
            await self.wait_job()
            rec = p.installed.get(42)
            self.assertEqual(rec["version"], "1.1")
            with open(os.path.join(rec["dir"], "game", "StarHop"), "rb") as f:
                self.assertEqual(f.read(), b"v2")
            with open(os.path.join(rec["dir"], "game", "settings.cfg")) as f:
                self.assertEqual(f.read(), "mine")
            self.assertEqual((await p.check_updates())["updates"], 0)
            r = await p.uninstall(42, False)
            self.assertTrue(r["ok"])
            self.assertFalse(os.path.exists(rec["dir"]))
            self.assertIsNone(p.installed.get(42))

    async def test_windows_galaxy_install(self):
        p = self.p
        plan = {"generation": 2, "build_id": "55", "version": "2.0", "install_dir": "Star Hop", "dirs": [], "links": [],
                "products": ["42"], "timestamp": "", "files": [{"path": "goggame-42.info", "sig": "a", "size": 0, "chunks": [], "product": "42"},
                                                               {"path": os.path.join("bin", "hop.exe"), "sig": "b", "size": 0, "chunks": [], "product": "42"}]}

        def fake_run(self_ex, old, free):
            os.makedirs(os.path.join(self_ex.dest, "bin"), exist_ok=True)
            with open(os.path.join(self_ex.dest, "goggame-42.info"), "w") as f:
                f.write('{"playTasks":[{"isPrimary":true,"path":"bin\\\\hop.exe","category":"game","type":"FileTask"}]}')
            open(os.path.join(self_ex.dest, "bin", "hop.exe"), "wb").close()
            return {"goggame-42.info": "a", os.path.join("bin", "hop.exe"): "b"}
        with mock.patch.object(api, "library", return_value=[{**GAME, "platforms": ["windows"]}]), \
                mock.patch.object(api, "owned_ids", return_value=[42]), \
                mock.patch.object(api, "product", return_value=product("2.0", 100, ("windows",))), \
                mock.patch.object(api, "builds", return_value=[{"build_id": "55", "branch": None, "link": "L", "generation": 2}]), \
                mock.patch.object(galaxy, "plan", return_value=plan), mock.patch.object(galaxy.Executor, "run", fake_run):
            await p.library(True)
            await p.install(42, "windows")
            await self.wait_job()
            rec = p.installed.get(42)
            self.assertIsNotNone(rec, EVENTS[-2:])
            self.assertEqual(rec["method"], "galaxy")
            self.assertEqual(rec["kind"], "windows")
            self.assertTrue(rec["exe"].endswith(os.path.join("bin", "hop.exe")))
            self.assertEqual(rec["build_id"], "55")
            self.assertEqual((await p.check_updates())["updates"], 0)
        with mock.patch.object(api, "builds", return_value=[{"build_id": "56", "branch": None, "link": "L", "generation": 2, "version_name": "2.1"}]):
            up = await p.check_updates()
            self.assertEqual(up["updates"], 1)
            self.assertEqual(up["installed"]["42"]["update_name"], "2.1")
        await p.uninstall(42, True)

    async def test_details_cached(self):
        d = {"id": 77, "description": ["Hi"], "screenshots": [], "videos": [], "genres": [], "themes": [], "modes": [],
             "developers": [], "publishers": [], "released": "", "rating": None, "languages": 0}
        with mock.patch.object(api, "details", return_value=dict(d)) as m:
            r1 = await self.p.details(77)
            r2 = await self.p.details(77)
        self.assertTrue(r1["ok"] and r2["ok"])
        self.assertEqual(r2["description"], ["Hi"])
        self.assertEqual(m.call_count, 1)
        with mock.patch.object(api, "details", side_effect=api.ApiError("down")), mock.patch.object(main, "DETAILS_TTL", -1):
            r3 = await self.p.details(77)   # stale cache still beats an error
        self.assertTrue(r3["ok"])
        with mock.patch.object(api, "details", side_effect=api.ApiError("down")):
            self.assertFalse((await self.p.details(78))["ok"])

    async def test_sign_in(self):
        p = self.p
        p.settings.data["auth"] = {}
        with mock.patch.object(api, "exchange_code", return_value={"access_token": "A", "refresh_token": "R", "expires": 9e12, "user_id": "9"}), \
                mock.patch.object(api, "user_data", return_value={"id": "9", "username": "roben", "avatar": ""}):
            bad = await p.sign_in("nope")
            self.assertFalse(bad["ok"])
            r = await p.sign_in("https://embed.gog.com/on_login_success?origin=client&code=" + "c" * 40)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["settings"]["signedIn"])
        self.assertNotIn("auth", r["settings"])
        self.assertEqual(r["settings"]["user"]["username"], "roben")
        out = await p.sign_out()
        self.assertFalse(out["signedIn"])

    async def test_token_refresh(self):
        p = self.p
        p.settings.data["auth"] = {"access_token": "old", "refresh_token": "r1", "expires": 0}
        with mock.patch.object(api, "refresh", return_value={"access_token": "new", "refresh_token": "r2", "expires": 9e12, "user_id": ""}) as m:
            self.assertEqual(p._token(), "new")
            self.assertEqual(p._token(), "new")
        self.assertEqual(m.call_count, 1)
        self.assertEqual(p.settings.data["auth"]["refresh_token"], "r2")


if __name__ == "__main__":
    unittest.main()
