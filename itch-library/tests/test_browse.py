import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))
from itchlib import api, browse  # noqa: E402

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Free games</title>
<item><title>Star Hop [Free] [Platformer] [Windows] [Linux]</title><plainTitle>Star Hop</plainTitle>
<link>https://dev.itch.io/star-hop</link><imageurl>https://img.itch.zone/a.png</imageurl><price>$0.00</price>
<platforms><windows>yes</windows><linux>yes</linux></platforms></item>
<item><title>Paid Thing [$4.99] [Action] [Windows]</title><link>https://other.itch.io/paid</link>
<description><![CDATA[<img src="https://img.itch.zone/b.png"> words]]></description></item>
<item><title>Browser Toy [Free] [HTML5]</title><link>https://x.itch.io/toy</link><platforms><web>yes</web></platforms></item>
</channel></rss>"""


class FeedUrl(unittest.TestCase):
    def test_default_is_gamepad(self):
        self.assertEqual(browse.feed_url(), "https://itch.io/games/input-gamepad.xml")

    def test_facets_sorted_and_unknown_dropped(self):
        u = browse.feed_url("top-rated", "on-sale", "puzzle", "x360", "linux", 3)
        self.assertEqual(u, "https://itch.io/games/top-rated/genre-puzzle/input-x360/on-sale/platform-linux.xml?page=3")
        self.assertEqual(browse.feed_url("bogus", "evil/..", "x", "", "mac"), "https://itch.io/games.xml")


class Parse(unittest.TestCase):
    def test_items(self):
        items = browse.parse_feed(FEED)
        a, b, c = items
        self.assertEqual((a["title"], a["free"], a["platforms"], a["cover"], a["author"]),
                         ("Star Hop", True, ["windows", "linux"], "https://img.itch.zone/a.png", "dev"))
        self.assertEqual((b["title"], b["price"], b["free"], b["platforms"], b["cover"]),
                         ("Paid Thing", "$4.99", False, ["windows"], "https://img.itch.zone/b.png"))
        self.assertEqual(c["platforms"], [])

    def test_browse_hides_web_only_known(self):
        with mock.patch.object(browse, "_get", return_value=FEED):
            browse._cache.clear()
            r = browse.browse(price="free")
        # "Browser Toy" lists only web, so it's dropped; unknown platforms would stay.
        self.assertEqual([i["title"] for i in r["items"]], ["Star Hop", "Paid Thing", "Browser Toy"])

    def test_bad_xml(self):
        with self.assertRaises(browse.BrowseError):
            browse.parse_feed(b"<html>nope")


class Resolve(unittest.TestCase):
    def test_rejects_other_hosts(self):
        for u in ("https://evil.com/x", "http://dev.itch.io/x", "https://itch.io/"):
            with self.assertRaises(browse.BrowseError):
                browse.resolve(u)

    def test_data_json(self):
        with mock.patch.object(browse, "_get", return_value=b'{"id": 1234, "title": "Star Hop"}') as g:
            self.assertEqual(browse.resolve("https://dev.itch.io/star-hop/"), 1234)
        g.assert_called_with("https://dev.itch.io/star-hop/data.json", 200_000)


class Search(unittest.TestCase):
    def test_maps_and_filters(self):
        d = {"games": [{"id": 1, "title": "A", "min_price": 0, "traits": ["p_linux"], "type": "default"},
                       {"id": 2, "title": "B", "min_price": 499, "traits": ["p_windows"], "type": "default"},
                       {"id": 3, "title": "Web", "min_price": 0, "traits": [], "type": "html"},
                       {"id": 4, "title": "Mac", "min_price": 0, "traits": ["p_osx"], "type": "default"}], "per_page": 20}
        with mock.patch.object(api, "get", return_value=d):
            r = browse.search("k", "abc")
        self.assertEqual([(i["id"], i["price"], i["free"]) for i in r["items"]], [(1, "Free", True), (2, "$4.99", False)])
        self.assertEqual(browse.search("k", "  ")["items"], [])


if __name__ == "__main__":
    unittest.main()
