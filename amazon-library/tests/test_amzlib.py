"""Manifest parsing/signing, sign-in helpers, fuel.json, and a full install/update/verify/uninstall
flow through the Plugin class with Amazon faked out (a throwaway RSA key stands in for Amazon's)."""
import asyncio, hashlib, io, logging, lzma, os, struct, sys, tempfile, types, unittest
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "py_modules"))
sys.path.insert(0, os.path.join(HERE, ".."))

TMP = tempfile.mkdtemp()
decky = types.ModuleType("decky")
decky.DECKY_USER_HOME = os.path.join(TMP, "home")
decky.DECKY_PLUGIN_SETTINGS_DIR = os.path.join(TMP, "settings")
decky.DECKY_PLUGIN_RUNTIME_DIR = os.path.join(TMP, "runtime")
decky.logger = logging.getLogger("amazon-test")
EVENTS = []
async def emit(event, *args):
    EVENTS.append((event, args))
decky.emit = emit
sys.modules["decky"] = decky
os.makedirs(decky.DECKY_USER_HOME, exist_ok=True)

import main  # noqa: E402
from amzlib import api, install, manifest  # noqa: E402

# --- a throwaway RSA key stands in for Amazon's when signing test manifests ---
def keypair():
    """Deterministic 1024-bit RSA key from Python's own primality test (Miller-Rabin)."""
    import random
    rnd = random.Random(42)

    def prime(bits):
        while True:
            c = rnd.getrandbits(bits) | (1 << (bits - 1)) | 1
            if all(pow(a, c - 1, c) == 1 for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
                return c
    e = 65537
    while True:
        p, q = prime(512), prime(512)
        phi = (p - 1) * (q - 1)
        try:
            d = pow(e, -1, phi)
            return p * q, e, d
        except ValueError:
            continue


KN, KE, KD = keypair()


def sign(data: bytes) -> bytes:
    k = (KN.bit_length() + 7) // 8
    digest = manifest.SHA256_PREFIX + hashlib.sha256(data).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    return pow(int.from_bytes(em, "big"), KD, KN).to_bytes(k, "big")


def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def fld(num, v):
    if isinstance(v, int):
        return varint(num << 3) + varint(v)
    return varint(num << 3 | 2) + varint(len(v)) + v


def build_manifest(files: dict, compress=True) -> bytes:
    """files: path -> bytes"""
    pkg = fld(1, b"main")
    for path, data in files.items():
        h = fld(1, 0) + fld(2, hashlib.sha256(data).digest())
        pkg += fld(2, fld(1, path.encode()) + fld(2, 0o644) + fld(3, len(data)) + fld(5, h))
    body = fld(1, pkg)
    payload = lzma.compress(body) if compress else body
    header = fld(1, fld(1, 1 if compress else 0)) + fld(3, fld(1, 0) + fld(2, sign(body)))
    return struct.pack(">I", len(header)) + header + payload


class Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeCDN:
    """Serves <base>/files/<sha256> for the current build."""
    def __init__(self):
        self.blobs = {}
        self.hits = 0

    def add(self, files):
        for d in files.values():
            self.blobs[hashlib.sha256(d).hexdigest()] = d

    def opener(self, *_a, **_k):
        cdn = self

        class O:
            def open(self, req, timeout=0):
                h = req.full_url.rsplit("/", 1)[-1]
                cdn.hits += 1
                return Resp(cdn.blobs[h])
        return O()


class Units(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.multiple(manifest, RSA_N=KN, RSA_E=KE)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_parse_and_verify(self):
        for comp in (True, False):
            raw = build_manifest({"Game\\Game.exe": b"MZ" + b"x" * 100, "data/a.pak": b"abc"}, comp)
            files = manifest.parse(raw)
            self.assertEqual([f["path"] for f in files], ["Game/Game.exe", "data/a.pak"])
            self.assertEqual(files[1]["size"], 3)
            self.assertEqual(files[1]["hash"], hashlib.sha256(b"abc").hexdigest())

    def test_bad_signature_rejected(self):
        raw = bytearray(build_manifest({"a": b"1"}, compress=False))
        raw[-1] ^= 1
        with self.assertRaises(manifest.ManifestError):
            manifest.parse(bytes(raw))

    def test_real_key_shape(self):
        self.p.stop()
        self.assertEqual(manifest.RSA_N.bit_length(), 2048)
        self.assertFalse(manifest.verify(b"x", b"\x00" * 256))
        self.p.start()

    def test_compare(self):
        a = [{"path": "x", "hash": "1"}, {"path": "y", "hash": "2"}]
        b = [{"path": "x", "hash": "1"}, {"path": "y", "hash": "3"}, {"path": "z", "hash": "4"}]
        fetch, remove = manifest.compare(b, a)
        self.assertEqual([f["path"] for f in fetch], ["y", "z"])
        self.assertEqual(remove, [])
        fetch, remove = manifest.compare(a[:1], b)
        self.assertEqual(fetch, [])
        self.assertEqual(sorted(remove), ["y", "z"])

    def test_code_from(self):
        url = "https://www.amazon.com/?openid.assoc_handle=amzn&openid.oa2.authorization_code=ANabcDEF123&openid.mode=id_res"
        self.assertEqual(api.code_from(url), "ANabcDEF123")
        self.assertEqual(api.code_from("  ANabcDEF123 "), "ANabcDEF123")
        self.assertEqual(api.code_from("https://www.amazon.com/"), "")

    def test_login_pkce(self):
        lg = api.new_login()
        import base64
        ch = base64.urlsafe_b64encode(hashlib.sha256(lg["verifier"].encode()).digest()).rstrip(b"=").decode()
        self.assertIn("code_challenge=" + ch, lg["url"])
        self.assertEqual(bytes.fromhex(lg["client_id"]).decode(), lg["serial"] + "#A2UMVHOX7UP4V7")

    def test_fuel_json5(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "Bin"))
        with open(os.path.join(d, "Bin", "Game.exe"), "wb") as f:
            f.write(b"MZ")
        with open(os.path.join(d, "fuel.json"), "w") as f:
            f.write('{\n // comment\n "SchemaVersion": "2",\n "Main": {"Command": "Bin\\\\Game.exe", "Args": ["-skip intro", "-x"],'
                    ' "WorkingSubdirOverride": "Bin",},\n "PostInstall": [{"Command": "vcredist.exe"}],\n}')
        fu = install.fuel(d)
        self.assertEqual(fu["exe"], os.path.join(d, "Bin", "Game.exe"))
        self.assertEqual(fu["cwd"], os.path.join(d, "Bin"))
        self.assertEqual(install.quote_args(fu["args"]), '"-skip intro" -x')
        self.assertEqual(fu["post"], 1)

    def test_safe_join(self):
        with self.assertRaises(install.InstallError):
            install.safe_join("/tmp/x", "../etc/passwd")
        self.assertEqual(install.safe_join("/tmp/x", "a\\b.txt"), "/tmp/x/a/b.txt")


class Flow(unittest.IsolatedAsyncioTestCase):
    async def test_install_update_verify_uninstall(self):
        p = main.Plugin()
        p.loop = asyncio.get_running_loop()
        p.settings.data["auth"] = {"access_token": "t", "refresh_token": "r", "expires": 9e12, "serial": "S",
                                   "user": {"id": "u1", "name": "Robin"}}
        cdn = FakeCDN()
        v1 = {"fuel.json": b'{"Main":{"Command":"Bin/Star.exe","Args":["-w"]}}', "Bin/Star.exe": b"MZ" + b"1" * 5000,
              "Data/old.pak": b"old"}
        v2 = {"fuel.json": v1["fuel.json"], "Bin/Star.exe": b"MZ" + b"2" * 5000, "Data/new.pak": b"new"}
        build = {"raw": build_manifest(v1), "ver": "v1"}
        cdn.add(v1)
        cdn.add(v2)
        game = {"id": "amzn1.adg.product.abc-123", "entitlement": "ent-1", "sku": "SKU1", "title": "Star Hop", "icon": "",
                "cover": "", "background": "", "logo": "", "short": "", "developer": "", "publisher": "", "genres": [],
                "released": "", "screenshot": "", "added": ""}

        def raw_req(url, *a, **k):
            if url.endswith("manifest.proto"):
                return build["raw"]
            raise AssertionError(url)

        with mock.patch.multiple(manifest, RSA_N=KN, RSA_E=KE), \
                mock.patch.object(api, "entitlements", return_value=[game]), \
                mock.patch.object(api, "game_download", side_effect=lambda t, e: {"url": "https://cdn.example/b", "version": build["ver"]}), \
                mock.patch.object(api, "request", side_effect=raw_req), \
                mock.patch.object(api, "sdk_channel", side_effect=api.ApiError("offline")), \
                mock.patch.object(api, "live_versions", side_effect=lambda t, ids: {i: build["ver"] for i in ids}), \
                mock.patch("urllib.request.build_opener", cdn.opener):
            r = await p.library(False)
            self.assertTrue(r["ok"], r)
            await p.install(game["id"])
            await p.worker
            done = [e for e in EVENTS if e[0] == "amazon_job_done"][-1][1][0]
            self.assertEqual(done["phase"], "done", done)
            rec = done["result"]
            self.assertTrue(rec["exe"].endswith("Bin/Star.exe"))
            self.assertEqual(rec["args"], "-w")
            self.assertIn('AMAZON_GAMES_FUEL_ENTITLEMENT_ID="ent-1"', rec["launch"])
            self.assertIn("%command% -w", rec["launch"])
            gdir = rec["dir"]
            self.assertTrue(gdir.endswith("Star-Hop-ctabc123"), gdir)
            open(os.path.join(gdir, "save.dat"), "w").write("mine")

            # Update: only changed files come down, dropped files go, saves stay.
            build.update(raw=build_manifest(v2), ver="v2")
            u = await p.check_updates()
            self.assertEqual(u["updates"], 1)
            hits = cdn.hits
            await p.install(game["id"])
            await p.worker
            done = [e for e in EVENTS if e[0] == "amazon_job_done"][-1][1][0]
            self.assertEqual(done["phase"], "done", done)
            self.assertEqual(cdn.hits - hits, 2)          # Star.exe + new.pak
            self.assertFalse(os.path.exists(os.path.join(gdir, "Data/old.pak")))
            self.assertEqual(open(os.path.join(gdir, "Data/new.pak"), "rb").read(), b"new")
            self.assertEqual(open(os.path.join(gdir, "save.dat")).read(), "mine")
            self.assertFalse(p.installed.get(game["id"]).get("update"))

            # Verify: a damaged file is re-downloaded, good ones aren't.
            open(os.path.join(gdir, "Bin/Star.exe"), "r+b").write(b"XX")
            hits = cdn.hits
            await p.install(game["id"], True)
            await p.worker
            self.assertEqual(cdn.hits - hits, 1)
            self.assertEqual(open(os.path.join(gdir, "Bin/Star.exe"), "rb").read(), v2["Bin/Star.exe"])

            r = await p.uninstall(game["id"], False)
            self.assertTrue(r["ok"])
            self.assertFalse(os.path.exists(gdir))
            self.assertIsNone(p.installed.get(game["id"]))

    async def test_cancel_first_install_leaves_nothing(self):
        p = main.Plugin()
        p.loop = asyncio.get_running_loop()
        p.settings.data["auth"] = {"access_token": "t", "refresh_token": "r", "expires": 9e12, "serial": "S", "user": {"id": "u2"}}
        files = {"Big.exe": b"MZ" + b"z" * 300000}
        game = {"id": "amzn1.adg.product.zzz-999", "entitlement": "e", "sku": "", "title": "Big", "icon": "", "cover": "",
                "background": "", "logo": "", "short": "", "developer": "", "publisher": "", "genres": [], "released": "",
                "screenshot": "", "added": ""}

        class Slow(Resp):
            def read(self, n=-1):
                job = p.jobs[0] if p.jobs else None
                if job:
                    job["cancel"].set()
                return super().read(1024)

        class O:
            def open(self, req, timeout=0):
                return Slow(files["Big.exe"])
        with mock.patch.multiple(manifest, RSA_N=KN, RSA_E=KE), \
                mock.patch.object(api, "entitlements", return_value=[game]), \
                mock.patch.object(api, "game_download", return_value={"url": "https://cdn.example/b", "version": "1"}), \
                mock.patch.object(api, "request", return_value=build_manifest(files)), \
                mock.patch.object(api, "sdk_channel", side_effect=api.ApiError("offline")), \
                mock.patch("urllib.request.build_opener", lambda *a, **k: O()):
            await p.library(True)
            await p.install(game["id"])
            await p.worker
        done = [e for e in EVENTS if e[0] == "amazon_job_done"][-1][1][0]
        self.assertEqual(done["phase"], "cancelled")
        self.assertFalse(os.path.exists(os.path.join(p._root(), install.slug("Big", game["id"]))))
        self.assertIsNone(p.installed.get(game["id"]))


if __name__ == "__main__":
    unittest.main()
