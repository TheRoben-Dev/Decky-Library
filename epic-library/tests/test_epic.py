"""Epic Library backend tests. Legendary is replaced by a fake lgd.py that behaves like it (same log
lines, same files), and the store endpoints are faked, so no network is needed."""
import asyncio, logging, os, shutil, stat, subprocess, sys, tempfile, textwrap, types, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "py_modules"))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp()
decky = types.ModuleType("decky")
decky.DECKY_USER_HOME = os.path.join(TMP, "home")
decky.DECKY_PLUGIN_SETTINGS_DIR = os.path.join(TMP, "settings")
decky.DECKY_PLUGIN_RUNTIME_DIR = os.path.join(TMP, "data")
decky.logger = logging.getLogger("epic-test")
EVENTS = []


async def emit(event, *args):
    EVENTS.append((event, args))
decky.emit = emit
sys.modules["decky"] = decky
os.makedirs(decky.DECKY_USER_HOME, exist_ok=True)

import main  # noqa: E402
from epiclib import catalog, legendary, library  # noqa: E402

# A stand-in for Legendary: answers the subcommands the plugin uses, writes the same files.
FAKE_LGD = textwrap.dedent(r'''
    import json, os, sys, time
    cfg = os.environ["LEGENDARY_CONFIG_PATH"]
    os.makedirs(cfg, exist_ok=True)
    a = sys.argv[1:]
    if a and a[0] == "-y":
        a = a[1:]
    log = lambda lvl, m: print(f"[cli] {lvl}: {m}", file=sys.stderr, flush=True)
    def rd(n, d):
        try: return json.load(open(os.path.join(cfg, n)))
        except Exception: return d
    def wr(n, v): json.dump(v, open(os.path.join(cfg, n), "w"))
    cmd = a[0]
    if cmd == "auth":
        if "--delete" in a: sys.exit(0)
        code = a[a.index("--code") + 1]
        if code != "0123456789abcdef0123456789abcdef":
            log("ERROR", "Login attempt failed, please see log for details."); sys.exit(0)
        wr("user.json", {"account_id": "acc1", "displayName": "Roben"})
    elif cmd == "list":
        if not rd("user.json", {}):
            print("Traceback (most recent call last):", file=sys.stderr)
            print("ValueError: No saved credentials", file=sys.stderr); sys.exit(1)
        wr("assets.json", {"Windows": [{"app_name": "Fish", "build_version": "2.0"}, {"app_name": "Owl", "build_version": "1.1"}]})
        print(json.dumps([
            {"app_name": "Owl", "app_title": "Owl Game", "asset_infos": {"Windows": "GameAsset(...)"},
             "metadata": {"namespace": "nsowl", "id": "cat1", "developer": "Owl Co",
                          "keyImages": [{"type": "DieselGameBoxTall", "url": "https://cdn1.epicgames.com/owl-tall.jpg"},
                                        {"type": "DieselGameBox", "url": "https://cdn1.epicgames.com/owl-wide.jpg"}],
                          "customAttributes": {"CloudSaveFolder": {"type": "STRING", "value": "x"}}},
             "dlcs": [{"app_name": "OwlDLC"}]},
            {"app_name": "Fish", "app_title": "Fish", "metadata": {"namespace": "nsfish"}, "dlcs": []},
            {"app_name": "EAThing", "app_title": "EA Thing", "metadata": {"namespace": "nsea",
             "customAttributes": {"ThirdPartyManagedApp": {"value": "The EA App"}}}},
        ]))
    elif cmd == "install":
        app = a[1]
        base = a[a.index("--base-path") + 1] if "--base-path" in a else ""
        inst = rd("installed.json", {})
        path = inst.get(app, {}).get("install_path") or os.path.join(base, app)
        log("INFO", f"Install path: {path}")
        if os.environ.get("FAKE_FAIL"):
            log("ERROR", "Not enough available disk space! 1.00 GiB < 5.00 GiB"); sys.exit(1)
        log("INFO", "Install size: 10.00 MiB")
        log("INFO", "Download size: 4.00 MiB (Compression savings: 60.0%)")
        for i in range(1, 5):
            if os.environ.get("FAKE_SLOW"): time.sleep(0.4)
            print(f"[DLM] INFO: = Progress: {i * 25:.02f}% ({i}/4), Running for 00:00:01, ETA: 00:00:00", file=sys.stderr, flush=True)
            print("[DLM] INFO:  + Download\t- 2.00 MiB/s (raw) / 4.00 MiB/s (decompressed)", file=sys.stderr, flush=True)
        os.makedirs(path, exist_ok=True)
        open(os.path.join(path, "Game.exe"), "w").write("MZ")
        ver = rd("assets.json", {}).get("Windows", [{}])
        ver = next((x["build_version"] for x in ver if x.get("app_name") == app), "1.0")
        inst[app] = {"app_name": app, "install_path": path, "title": app, "version": ver,
                     "executable": "Game.exe", "install_size": 10485760, "is_dlc": False, "can_run_offline": True}
        wr("installed.json", inst)
        log("INFO", "Finished installation process in 1.00 seconds.")
    elif cmd == "uninstall":
        inst = rd("installed.json", {})
        rec = inst.pop(a[1], None)
        if rec:
            import shutil; shutil.rmtree(rec["install_path"], ignore_errors=True)
        wr("installed.json", inst)
    elif cmd == "list-installed":
        wr("assets.json", {"Windows": [{"app_name": "Fish", "build_version": "2.0"}, {"app_name": "Owl", "build_version": "1.2"}]})
        print("[]")
    elif cmd == "info":
        print(json.dumps({"game": {}, "install": None, "manifest": {"disk_size": 1234, "download_size": 567}}))
    elif cmd == "launch":
        if "--offline" not in a and os.environ.get("FAKE_OFFLINE"):
            log("ERROR", "Login failed, cannot continue!"); sys.exit(1)
        print(json.dumps({"game_parameters": ["-gameflag"], "user_parameters": [],
                          "egl_parameters": ["-AUTH_LOGIN=unused", "-AUTH_PASSWORD=" + ("" if "--offline" in a else "tok"),
                                             "-epicovt=/tmp/x/a.ovt", "-epicusername=Ro ben"]}))
    else:
        log("ERROR", f"unknown {cmd}"); sys.exit(2)
''')


def make_runtime(dest):
    shutil.copytree(os.path.join(ROOT, "runtime"), dest, ignore=shutil.ignore_patterns("site", "__pycache__"))
    with open(os.path.join(dest, "lgd.py"), "w") as f:
        f.write(FAKE_LGD)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Helpers(unittest.TestCase):
    def test_extract_code(self):
        c = "0123456789abcdef0123456789abcdef"
        self.assertEqual(main.extract_code(c), c)
        self.assertEqual(main.extract_code('{"redirectUrl":"https://x","authorizationCode":"%s","sid":null}' % c.upper()), c)
        self.assertEqual(main.extract_code("  \n" + c + "\n"), c)
        self.assertEqual(main.extract_code("nope"), "")
        self.assertEqual(main.extract_code("0123"), "")

    def test_last_error(self):
        self.assertEqual(legendary.last_error("[cli] INFO: x\n[cli] ERROR: Boom happened\n"), "Boom happened")
        self.assertEqual(legendary.last_error("Traceback (most recent call last):\n  File x\nValueError: No saved credentials\n"), "Not signed in")

    def test_library_trim(self):
        raw = [{"app_name": "A", "app_title": "Alpha", "metadata": {"namespace": "n", "keyImages": [
                   {"type": "Thumbnail", "url": "t"}, {"type": "DieselGameBoxTall", "url": "tall"}]}},
               {"app_name": "D", "app_title": "Dlc", "metadata": {"mainGameItem": {}}},
               {"app_name": "B", "app_title": "beta", "metadata": {"customAttributes": {"ThirdPartyManagedProvider": {"value": "Origin"}}}},
               "junk"]
        out = library.build(raw, {"A": "1", "B": "2"})
        self.assertEqual([g["app"] for g in out], ["A", "B"])
        self.assertEqual(out[0]["tall"], "tall")
        self.assertTrue(out[0]["installable"])
        self.assertFalse(out[1]["installable"])
        self.assertEqual(out[1]["third_party"], "Origin")

    def test_non_games_excluded(self):
        raw = [{"app_name": "G", "app_title": "Game", "metadata": {"namespace": "a", "categories": [{"path": "games"}, {"path": "applications"}]}},
               {"app_name": "Asset", "app_title": "Rock pack", "metadata": {"namespace": "b", "categories": [{"path": "assets/textures"}]}},
               {"app_name": "Plug", "app_title": "Plugin", "metadata": {"namespace": "c", "categories": [{"path": "plugins/engine"}]}},
               {"app_name": "App", "app_title": "Some app", "metadata": {"namespace": "d", "categories": [{"path": "applications"}]}},
               {"app_name": "UE", "app_title": "UE thing", "metadata": {"namespace": "ue"}},
               {"app_name": "Bare", "app_title": "No categories", "metadata": {"namespace": "e"}}]
        self.assertEqual([g["app"] for g in library.build(raw, {})], ["G", "Bare"])

    def test_installed_view(self):
        v = library.installed_view({"A": {"install_path": "/g/A", "title": "A", "version": "1", "executable": "\\bin\\a.exe"},
                                    "X": {"is_dlc": True}}, {"A": {"appid": 5}}, {"A": "2"}, lambda p: True)
        self.assertEqual(list(v), ["A"])
        self.assertEqual(v["A"]["exe"], "/g/A/bin/a.exe")
        self.assertTrue(v["A"]["update"])
        self.assertEqual(v["A"]["appid"], 5)


class Catalog(unittest.TestCase):
    EL = {"title": "Pad Game", "id": "o1", "namespace": "ns1", "productSlug": "pad-game",
          "keyImages": [{"type": "OfferImageTall", "url": "https://cdn1.epicgames.com/p.jpg"}],
          "seller": {"name": "Pads"}, "tags": [{"id": "9"}, {"id": "1"}],
          "price": {"totalPrice": {"discountPrice": 500, "originalPrice": 1000, "fmtPrice": {"discountPrice": "$5.00", "originalPrice": "$10.00"}}}}

    def test_item(self):
        it = catalog.item(self.EL, "9", "en-US")
        self.assertEqual(it["url"], "https://store.epicgames.com/en-US/p/pad-game")
        self.assertEqual((it["price"], it["sale"], it["controller"], it["free"]), ("$5.00", 50, True, False))
        self.assertEqual(it["checkout"], "https://store.epicgames.com/purchase?offers=1-ns1-o1")
        e = dict(self.EL, productSlug=None, urlSlug="0123456789abcdef0123456789abcdef", customAttributes=[])
        self.assertIn("browse?q=Pad%20Game", catalog.item(e, "", "en-US")["url"])

    def test_tags_and_search(self):
        cache = tempfile.mkdtemp()
        calls = []

        def fake(query, v):
            calls.append((query, dict(v)))
            if "catalogTags" in query:
                return {"Catalog": {"tags": {"elements": [
                    {"id": "9", "name": "Controller Support", "referenceCount": 50, "status": "ACTIVE"},
                    {"id": "99", "name": "Controller Support", "referenceCount": 2},
                    {"id": "3", "name": "Action"}, {"id": "4", "name": "Puzzle"}]}}}
            if "freeGame" in query:
                raise catalog.CatalogError('Epic store: Unknown argument "freeGame" on field "searchStore"')
            return {"Catalog": {"searchStore": {"elements": [self.EL, dict(self.EL, id="o2", price={"totalPrice": {"discountPrice": 0, "originalPrice": 0}})],
                                                "paging": {"total": 100}}}}
        with mock.patch.object(catalog, "_graphql", side_effect=fake):
            r = catalog.search({"controller": True, "genre": "3", "price": "free", "country": "se", "page": 2}, cache)
        search_calls = [c for c in calls if "searchStore" in c[0]]
        self.assertEqual(search_calls[0][1]["tag"], "9|3")
        self.assertEqual(search_calls[0][1]["start"], 40)
        self.assertEqual(search_calls[0][1]["country"], "SE")
        self.assertNotIn("freeGame", search_calls[1][1])         # retried without the unknown argument
        self.assertEqual([i["id"] for i in r["items"]], ["o2"])   # and filtered here instead
        self.assertTrue(r["more"])
        self.assertEqual(r["genres"], [["3", "Action"], ["4", "Puzzle"]])
        # Tags are cached: a second search doesn't ask again.
        with mock.patch.object(catalog, "_graphql", side_effect=fake):
            catalog.search({}, cache)
        self.assertEqual(sum(1 for c in calls if "catalogTags" in c[0]), 1)

    def test_free_now(self):
        el = dict(self.EL, promotions={"promotionalOffers": [{"promotionalOffers": [
            {"startDate": "2000-01-01T00:00:00.000Z", "endDate": "2999-01-01T00:00:00.000Z", "discountSetting": {"discountPercentage": 0}}]}]})
        el2 = dict(self.EL, id="later", promotions={"promotionalOffers": [], "upcomingPromotionalOffers": []})
        with mock.patch.object(catalog, "_request", return_value={"data": {"Catalog": {"searchStore": {"elements": [el, el2]}}}}):
            out = catalog.free_now("us")
        self.assertEqual([i["id"] for i in out], ["o1"])
        self.assertEqual(out[0]["price"], "Free")


class StoreDetails(unittest.TestCase):
    def test_plain(self):
        t = catalog.plain("# Title\n\n**Bold** text with [a link](https://x) ![img](https://y)<br>next&amp;more\n\n- one\n- two")
        self.assertEqual(t, "Title\n\nBold text with a link\nnext&more\n\n• one\n• two")

    def test_details_merges_sources_and_caches(self):
        cache = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, cache, True)
        offer = {"title": "G", "longDescription": "Long **story**", "developerDisplayName": "Dev", "publisherDisplayName": "Pub",
                 "releaseDate": "2020-09-17T15:00:00.000Z",
                 "keyImages": [{"type": "OfferImageWide", "url": "https://cdn1.epicgames.com/w.jpg"},
                               {"type": "Screenshot", "url": "https://cdn1.epicgames.com/s0.jpg"}],
                 "tags": [{"name": "Action", "groupName": "genre"}, {"name": "Controller Support", "groupName": "feature"},
                          {"name": "Windows", "groupName": "platform"}, {"name": "Odd", "groupName": "other"}],
                 "price": {"totalPrice": {"discountPrice": 0, "fmtPrice": {"discountPrice": "0", "originalPrice": "$24.99"}}}}
        cms = {"pages": [{"type": "productHome", "data": {
            "gallery": {"galleryImages": [{"src": "https://cdn1.epicgames.com/s1.jpg"}, {"src": "https://cdn1.epicgames.com/s0.jpg"}]},
            "requirements": {"systems": [{"systemType": "Windows", "details": [{"title": "OS", "minimum": "Windows 10", "recommended": ""}]}]}}}]}
        calls = []

        def gql(query, v):
            calls.append(query)
            if "getProductResult" in query:
                return {"RatingsPolls": {"getProductResult": {"averageRating": 4.666}}}
            return {"Catalog": {"catalogOffer": offer}}
        with mock.patch.object(catalog, "_graphql", side_effect=gql), mock.patch.object(catalog, "_request", return_value=cms):
            d = catalog.details("ns1", "o1", "hades", "se", "en-US", cache)
            catalog.details("ns1", "o1", "hades", "se", "en-US", cache)
        self.assertEqual(len(calls), 2)                      # second call came from the cache
        self.assertEqual(d["description"], "Long story")
        self.assertEqual(d["shots"], ["https://cdn1.epicgames.com/s0.jpg", "https://cdn1.epicgames.com/s1.jpg"])
        self.assertEqual((d["genres"], d["features"], d["platforms"]), (["Action"], ["Controller Support"], ["Windows"]))
        self.assertEqual(d["requirements"], [["OS", "Windows 10", ""]])
        self.assertEqual((d["rating"], d["released"], d["price"], d["developer"]), (4.7, "2020-09-17", "Free", "Dev"))

    def test_details_survives_missing_sources(self):
        cache = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, cache, True)

        def gql(query, v):
            if "longDescription" in query:
                raise catalog.CatalogError('Epic store: Cannot query field "longDescription"')
            if "getProductResult" in query:
                raise catalog.CatalogError("nope")
            return {"Catalog": {"catalogOffer": {"title": "G", "description": "Short",
                                                 "keyImages": [{"type": "OfferImageWide", "url": "https://cdn1.epicgames.com/w.jpg"}]}}}
        with mock.patch.object(catalog, "_graphql", side_effect=gql), \
                mock.patch.object(catalog, "_request", side_effect=catalog.CatalogError("404", 404)):
            d = catalog.details("ns1", "o2", "", "US", "en-US", cache)
        self.assertEqual((d["description"], d["shots"], d["rating"]), ("Short", ["https://cdn1.epicgames.com/w.jpg"], 0.0))
        with self.assertRaises(catalog.CatalogError):
            catalog.details("../x", "o", "", "US", "en-US", cache)


class PluginFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.p = main.Plugin()
        src = os.path.join(TMP, "plugin-runtime")
        make_runtime(src)
        with mock.patch.object(main, "PLUGIN_DIR", TMP):
            os.makedirs(os.path.join(TMP, "runtime"), exist_ok=True)
            shutil.rmtree(os.path.join(TMP, "runtime"))
            shutil.copytree(src, os.path.join(TMP, "runtime"))
            with open(os.path.join(TMP, "package.json"), "w") as f:
                f.write("{}")
            cls.loop.run_until_complete(cls.p._main())

    def r(self, coro):
        return self.loop.run_until_complete(coro)

    def wait_jobs(self):
        for _ in range(200):
            if not self.p.jobs and (not self.p.worker or self.p.worker.done()):
                return
            self.r(asyncio.sleep(0.05))
        self.fail("job didn't finish")

    def test_1_runtime_installed(self):
        rt = self.p.runtime
        self.assertTrue(os.path.isfile(os.path.join(rt, "launch.sh")))
        self.assertTrue(os.access(os.path.join(rt, "launch.sh"), os.X_OK))
        env = open(os.path.join(rt, "paths.env")).read()
        self.assertIn("EPIC_CONFIG=", env)
        self.assertEqual(stat.S_IMODE(os.stat(self.p.lgd.config).st_mode), 0o700)
        self.assertEqual(self.p.launch_options("Owl"), f'"{rt}/launch.sh" Owl %command%')

    def test_2_sign_in(self):
        s = self.r(self.p.settings_get())
        self.assertFalse(s["signedIn"])
        self.assertEqual(s["problem"], "")
        r = self.r(self.p.library(False))
        self.assertFalse(r["ok"])
        r = self.r(self.p.sign_in("ffffffffffffffffffffffffffffffff"))
        self.assertFalse(r["ok"])
        r = self.r(self.p.sign_in('{"authorizationCode":"0123456789abcdef0123456789abcdef"}'))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["settings"]["user"]["name"], "Roben")

    def test_3_library(self):
        r = self.r(self.p.library(True))
        self.assertTrue(r["ok"], r)
        self.assertEqual([g["app"] for g in r["games"]], ["Fish", "Owl"])   # EA game hidden by default
        owl = r["games"][1]
        self.assertTrue(owl["cloud_saves"])
        self.assertEqual(owl["dlcs"], 1)
        g = self.r(self.p.game("Owl"))
        self.assertTrue(g["ok"] and g["installed"] is None)
        info = self.r(self.p.install_info("Owl"))
        self.assertEqual((info["disk"], info["download"]), (1234, 567))

    def test_4_install_update_uninstall(self):
        EVENTS.clear()
        self.r(self.p.install("Owl"))
        self.wait_jobs()
        done = [a[0] for e, a in EVENTS if e == "epic_job_done"]
        self.assertEqual(done[-1]["phase"], "done", done)
        res = done[-1]["result"]
        self.assertTrue(res["exe"].endswith("/Owl/Game.exe"))
        self.assertTrue(res["dir"].startswith(os.path.join(decky.DECKY_USER_HOME, "Games", "epic")))
        phases = [a[0][0]["phase"] for e, a in EVENTS if e == "epic_job" and a[0]]
        self.assertIn("downloading", phases)
        sc = self.r(self.p.shortcut_info("Owl"))
        self.assertTrue(sc["ok"])
        self.r(self.p.set_shortcut("Owl", 777))
        self.assertEqual(self.r(self.p.installed_list())["Owl"]["appid"], 777)
        # Update check sees the newer build.
        u = self.r(self.p.check_updates())
        self.assertEqual(u["updates"], 1)
        self.assertTrue(u["installed"]["Owl"]["update"])
        self.r(self.p.install("Owl"))
        self.wait_jobs()
        self.assertFalse(self.r(self.p.installed_list())["Owl"]["update"])
        # Uninstall, deleting the prefix.
        pfx = os.path.join(decky.DECKY_USER_HOME, ".local/share/Steam/steamapps/compatdata/777")
        os.makedirs(pfx)
        r = self.r(self.p.uninstall("Owl", True))
        self.assertEqual(r, {"ok": True, "appid": 777})
        self.assertFalse(os.path.exists(pfx))
        self.assertNotIn("Owl", self.r(self.p.installed_list()))

    def test_5_failure_and_cancel(self):
        EVENTS.clear()
        with mock.patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            self.r(self.p.install("Fish"))
            self.wait_jobs()
        done = [a[0] for e, a in EVENTS if e == "epic_job_done"][-1]
        self.assertEqual(done["phase"], "error")
        self.assertIn("Not enough available disk space", done["error"])
        EVENTS.clear()
        with mock.patch.dict(os.environ, {"FAKE_SLOW": "1"}):
            self.r(self.p.install("Fish"))
            for _ in range(100):
                if self.p.jobs and self.p.jobs[0]["phase"] == "downloading":
                    break
                self.r(asyncio.sleep(0.05))
            self.r(self.p.cancel("Fish"))
            self.wait_jobs()
        done = [a[0] for e, a in EVENTS if e == "epic_job_done"][-1]
        self.assertEqual(done["phase"], "cancelled")
        self.assertTrue(self.p.meta.get("Fish").get("partial", "").endswith("/Fish"))
        self.assertTrue(self.r(self.p.discard("Fish"))["ok"])
        self.assertFalse(os.path.exists(os.path.join(decky.DECKY_USER_HOME, "Games", "epic", "Fish")))

    def test_6_third_party_refused(self):
        self.r(self.p.set_options({"show_all": True}))
        r = self.r(self.p.library(True))
        self.assertIn("EAThing", [g["app"] for g in r["games"]])
        r = self.r(self.p.install("EAThing"))
        self.assertFalse(r["ok"])
        self.assertIn("EA App", r["error"])
        self.r(self.p.set_options({"show_all": False}))

    def test_7_launch_wrapper(self):
        launch = os.path.join(self.p.runtime, "launch.sh")
        echo = os.path.join(TMP, "echo-args.sh")
        with open(echo, "w") as f:
            f.write('#!/bin/bash\nfor a in "$@"; do printf "<%s>" "$a"; done\n')
        os.chmod(echo, 0o755)
        env = dict(os.environ, LD_PRELOAD="", HOME=decky.DECKY_USER_HOME)
        out = subprocess.run([launch, "Owl", echo, "waitforexitandrun", "/g/Owl/Game.exe"], env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "<waitforexitandrun></g/Owl/Game.exe><-gameflag><-AUTH_LOGIN=unused>"
                                     "<-AUTH_PASSWORD=tok><-epicovt=Z:\\tmp\\x\\a.ovt><-epicusername=Ro ben>")
        out = subprocess.run([launch, "Owl", echo, "x.exe"], env=dict(env, FAKE_OFFLINE="1"),
                             capture_output=True, text=True, timeout=60)
        self.assertIn("<-AUTH_PASSWORD=>", out.stdout)
        log = open(os.path.join(self.p.data, "logs", "launch.log")).read()
        self.assertIn("launching offline", log)

    def test_8_sign_out(self):
        s = self.r(self.p.sign_out())
        self.assertFalse(s["signedIn"])


if __name__ == "__main__":
    unittest.main()
