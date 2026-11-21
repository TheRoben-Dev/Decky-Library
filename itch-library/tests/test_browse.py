import os, sys, time, unittest
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


class Filters(unittest.TestCase):
    def test_full_facets(self):
        u = browse.feed_url("newest", "store", "", "gamepad", "", released="last-30-days", duration="half-hour",
                            multiplayer="local-multiplayer", accessibility="subtitles", engine="godot",
                            tags=["Pixel Art", "roguelike"], demo=True)
        self.assertEqual(u, "https://itch.io/games/newest/accessibility-subtitles/duration-half-hour/has-demo/"
                            "input-gamepad/last-30-days/local-multiplayer/made-with-godot/store/tag-pixel-art/tag-roguelike.xml")

    def test_unknown_values_and_bad_tags_dropped(self):
        u = browse.feed_url(controller="", duration="forever", engine="../x", tags=["../..", "", "a" * 60])
        self.assertEqual(u, "https://itch.io/games.xml")

    def test_adult_tags_need_opt_in(self):
        self.assertEqual(browse.feed_url(controller="", tags=["nsfw", "horror"]), "https://itch.io/games/tag-horror.xml")
        self.assertEqual(browse.feed_url(controller="", tags=["nsfw"], adult=True), "https://itch.io/games/tag-nsfw.xml")


class RateLimit(unittest.TestCase):
    def setUp(self):
        browse._cache.clear()
        browse.SITE_THROTTLE.until = 0
        browse.SITE_THROTTLE.last = 0

    tearDown = setUp

    def _http429(self, retry="30"):
        import email.message, urllib.error
        h = email.message.Message()
        h["Retry-After"] = retry
        return urllib.error.HTTPError("https://itch.io/games.xml", 429, "Too Many Requests", h, None)

    def test_429_sets_cooldown_and_blocks_further_requests(self):
        opener = mock.Mock()
        opener.open.side_effect = self._http429("30")
        with mock.patch.object(api, "_opener", return_value=opener):
            with self.assertRaises(browse.BrowseError) as c:
                browse.browse()
            self.assertEqual((c.exception.status, c.exception.retry_after), (429, 30))
            self.assertIn("Try again in 30 s", str(c.exception))
            with self.assertRaises(browse.BrowseError):
                browse.browse(price="free")
        self.assertEqual(opener.open.call_count, 1)   # the second one never left the device

    def test_stale_results_shown_while_limited(self):
        with mock.patch.object(browse, "_get", return_value=FEED):
            first = browse.browse()
        url = browse.feed_url()
        browse._cache[url] = (time.time() - browse.CACHE_TTL - 5, first)
        with mock.patch.object(browse, "_get", side_effect=browse.BrowseError("limited", 429, 60)):
            r = browse.browse()
        self.assertEqual(r["items"], first["items"])
        self.assertIn("earlier", r["notice"])

    def test_retry_after_parsing(self):
        self.assertEqual(api.retry_after({"Retry-After": "120"}), 120)
        self.assertEqual(api.retry_after({"Retry-After": "1"}), 5)
        self.assertEqual(api.retry_after({}), 60)
        self.assertEqual(api.retry_after({"Retry-After": "99999"}), 900)
