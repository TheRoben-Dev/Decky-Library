"""Install / update / uninstall through the Plugin class with itch.io faked out."""
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
decky.logger = logging.getLogger("itch-test")
EVENTS = []
async def emit(event, *args):
    EVENTS.append((event, args))
decky.emit = emit
sys.modules["decky"] = decky
os.makedirs(decky.DECKY_USER_HOME, exist_ok=True)

import main  # noqa: E402
from itchlib import api  # noqa: E402

ELF64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + (2).to_bytes(2, "little") + (0x3E).to_bytes(2, "little") + b"\x00" * 4000


def zip_bytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data, mode in files:
            zi = zipfile.ZipInfo(name); zi.external_attr = mode << 16
            z.writestr(zi, data)
    return b.getvalue()


def rd(p):
    with open(p) as f:
        return f.read()


class Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data); self.headers = {"Content-Length": str(len(data))}


GAME = {"id": 42, "title": "Star Hop", "key": 7, "still": "", "cover": "", "url": "", "short": "", "author": "", "platforms": ["linux"], "classification": "game"}


class Flow(unittest.IsolatedAsyncioTestCase):
    async def test_install_update_uninstall(self):
        p = main.Plugin()
        p.settings.data["key"] = "k" * 30
        p.loop = asyncio.get_running_loop()
        state = {"build": 1, "files": [("StarHop/StarHop.x86_64", ELF64, 0o100755), ("StarHop/data.pck", b"v1", 0o100644)]}

        def uploads(key, gid, dk):
            return [api.upload_info({"id": 9, "filename": "starhop-linux.zip", "size": 0, "storage": "build", "type": "default",
                                     "build_id": state["build"], "traits": ["p_linux"]})]
        with mock.patch.object(api, "owned", return_value=[GAME]), mock.patch.object(api, "uploads", side_effect=uploads), \
                mock.patch.object(api, "open_download", side_effect=lambda *a, **k: Resp(zip_bytes(state["files"]))):
            lib = await p.library(True)
            self.assertTrue(lib["ok"]); self.assertEqual(lib["games"][0]["id"], 42)
            r = await p.install(42, 0)
            self.assertTrue(r["ok"])
            await p.worker
            done = [a[0] for e, a in EVENTS if e == "itch_job_done"][-1]
            self.assertEqual(done["phase"], "done", done)
            rec = done["result"]
            self.assertTrue(rec["exe"].endswith("StarHop/StarHop.x86_64"))
            self.assertEqual(rec["kind"], "linux")
            self.assertTrue(os.access(rec["exe"], os.X_OK))
            # The game writes a save into its folder.
            save = os.path.join(rec["dir"], "StarHop", "save.dat")
            with open(save, "w") as f:
                f.write("progress")
            await p.set_shortcut(42, 123456)

            state["build"] = 2
            state["files"] = [("StarHop/StarHop.x86_64", ELF64, 0o100755), ("StarHop/data.pck", b"v2", 0o100644)]
            u = await p.check_updates()
            self.assertEqual(u["updates"], 1)
            await p.install(42, 0)
            await p.worker
            done = [a[0] for e, a in EVENTS if e == "itch_job_done"][-1]
            self.assertEqual((done["phase"], done["action"]), ("done", "update"), done)
            self.assertEqual(rd(os.path.join(rec["dir"], "StarHop", "data.pck")), "v2")
            self.assertEqual(rd(save), "progress")
            self.assertEqual(done["result"]["appid"], 123456)
            self.assertFalse(done["result"]["update"])
            self.assertEqual((await p.check_updates())["updates"], 0)

            r = await p.uninstall(42, False)
            self.assertEqual(r, {"ok": True, "appid": 123456})
            self.assertFalse(os.path.exists(rec["dir"]))
            self.assertEqual(await p.installed_list(), {})

    async def test_cancel_queued(self):
        p = main.Plugin()
        p.settings.data["key"] = "k" * 30
        p.loop = asyncio.get_running_loop()
        with mock.patch.object(api, "owned", return_value=[GAME]):
            await p.library(True)
        with mock.patch.object(p, "_work", new=mock.AsyncMock()):
            await p.install(42, 0)
            jobs = await p.cancel(42)
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
