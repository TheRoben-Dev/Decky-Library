"""The backend must load in Decky's bundled Python, which ships only part of the standard library.

0.2.0 imported xml.etree at the top level; where that module is missing the backend never
starts and every screen waits forever. This loads main.py with such modules blocked."""
import os, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
# Not in Decky's PyInstaller bundle unless the loader itself happens to pull them in.
MISSING = ["xml", "tarfile", "secrets", "html.parser", "lzma", "bz2", "uuid"]

SCRIPT = r"""
import importlib.abc, logging, sys, types
BLOCK = set(sys.argv[1].split(","))
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name in BLOCK or name.split(".")[0] in BLOCK:
            raise ImportError("not bundled: " + name)
for m in list(sys.modules):
    if m in BLOCK or m.split(".")[0] in BLOCK:
        del sys.modules[m]
sys.meta_path.insert(0, Block())
d = types.ModuleType("decky")
d.DECKY_USER_HOME = d.DECKY_PLUGIN_SETTINGS_DIR = d.DECKY_PLUGIN_RUNTIME_DIR = sys.argv[2]
d.logger = logging.getLogger("t")
async def emit(*a): pass
d.emit = emit
sys.modules["decky"] = d
sys.path.insert(0, sys.argv[3])
import main
main.Plugin()
from itchlib import browse
browse.parse_feed(b"<rss><channel><item><title>A</title><link>https://a.itch.io/b</link></item></channel></rss>")
print("ok")
"""


class BundledPython(unittest.TestCase):
    def test_backend_loads_without_optional_stdlib(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, "-I", "-c", SCRIPT, ",".join(MISSING), tmp, ROOT],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "ok", r.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
