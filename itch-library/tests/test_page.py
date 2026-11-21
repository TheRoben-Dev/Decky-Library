"""Store details parsed from a game's itch.io page."""
import os, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from itchlib import browse, page  # noqa: E402

HTML = b"""<html><head><title>Star Hop by dev</title></head><body>
<div class="video_embed"><iframe src="https://www.youtube.com/embed/abcDEF12345?wmode=opaque"></iframe></div>
<div class="formatted_description user_formatted">
<h2>About</h2><p>Hop between <b>stars</b> &amp; dodge comets.</p>
<div><p>Nested <i>div</i> text.</p></div>
<ul><li>Gamepad support</li><li>Local co-op</li></ul>
<p><img src="https://img.itch.zone/abc/gif.gif"><img src="https://evil.example/x.png"></p>
<script>alert(1)</script><p onclick="x()">Last line</p>
</div>
<div class="screenshot_list">
<a href="https://img.itch.zone/s1/original.png" data-image_lightbox="true"><img src="https://img.itch.zone/s1/347x500.png"></a>
<a href="https://img.itch.zone/s2/original.png"><img src="x"></a>
<a href="javascript:alert(1)"><img src="x"></a>
</div>
<div class="more_information_toggle"><div class="info_panel_wrapper"><div class="game_info_panel_widget base_widget">
<table><tbody>
<tr><td>Status</td><td>Released</td></tr>
<tr><td>Platforms</td><td><a href="/games/platform-windows">Windows</a>, <a href="/games/platform-linux">Linux</a></td></tr>
<tr><td>Rating</td><td><div class="star_value" itemprop="ratingValue" content="4.6"></div><span itemprop="ratingCount" content="88">(88)</span></td></tr>
<tr><td>Inputs</td><td>Keyboard, Xbox controller, Gamepad (any)</td></tr>
<tr><td>Links</td><td><a href="https://x">Steam</a></td></tr>
</tbody></table></div></div></div>
</body></html>"""


class Parse(unittest.TestCase):
    def test_page(self):
        p = page.parse(HTML.decode())
        texts = [(b["t"], b.get("text") or b.get("src")) for b in p["description"]]
        self.assertEqual(texts, [("h", "About"), ("p", "Hop between stars & dodge comets."), ("p", "Nested div text."),
                                 ("li", "Gamepad support"), ("li", "Local co-op"),
                                 ("img", "https://img.itch.zone/abc/gif.gif"), ("p", "Last line")])
        self.assertEqual(p["screenshots"], ["https://img.itch.zone/s1/original.png", "https://img.itch.zone/s2/original.png"])
        self.assertEqual(dict(p["info"])["Platforms"], "Windows, Linux")
        self.assertEqual(dict(p["info"])["Inputs"], "Keyboard, Xbox controller, Gamepad (any)")
        self.assertNotIn("Links", dict(p["info"]))
        self.assertEqual(p["rating"], {"value": 4.6, "count": 88})
        self.assertEqual(p["video"], "https://www.youtube.com/watch?v=abcDEF12345")

    def test_empty_page_is_harmless(self):
        self.assertEqual(page.parse("<html></html>"),
                         {"description": [], "screenshots": [], "info": [], "rating": {}, "video": ""})


class Cache(unittest.TestCase):
    def setUp(self):
        page._mem.clear()
        self.dir = tempfile.mkdtemp()

    def test_fetched_once_then_cached_on_disk(self):
        with mock.patch.object(browse, "_get", return_value=HTML) as g:
            a = page.store_page("https://dev.itch.io/star-hop/", self.dir)
            page._mem.clear()
            b = page.store_page("https://dev.itch.io/star-hop", self.dir)
        self.assertEqual(g.call_count, 1)
        g.assert_called_with("https://dev.itch.io/star-hop", page.MAX_PAGE)
        self.assertEqual(a, b)

    def test_stale_copy_when_refused(self):
        with mock.patch.object(browse, "_get", return_value=HTML):
            page.store_page("https://dev.itch.io/star-hop", self.dir)
        for e in page._mem.values():
            e["at"] = time.time() - page.TTL - 1
        with mock.patch.object(browse, "_get", side_effect=browse.BrowseError("limited", 429, 60)):
            r = page.store_page("https://dev.itch.io/star-hop", self.dir)
        self.assertTrue(r["stale"])
        self.assertTrue(r["screenshots"])

    def test_rejects_non_itch(self):
        with self.assertRaises(browse.BrowseError):
            page.store_page("https://evil.example/game")
