import unittest

from verify_coordinates import article_id, check_scene, guard, match_spots, parse_article, sanity, update_pins

HTML = """<div class="article-body-inner">
今日は駅に来ました。<br>座標: 38.1, 140.1<br>
六郷土手河川敷公園<br>〒144-0045 東京都大田区南六郷2丁目<br>座標: 35.543623, 139.722340<br>
感想の一文です。<br>〒981-0213 宮城県松島町1-1<br>写真を撮りました。<br>座標: 38.3, 141.0<br>
</div>"""
URL = "http://blog.livedoor.jp/fumichen2/archives/1.html"


def scene(**kw):
    return {"id": "a", "name": "六郷土手河川敷公園", "address": "東京都大田区南六郷2丁目", "source_url": URL, "lat": 35.543623, "lng": 139.72234, **kw}


def snap():
    return {"articles": {"1": {"spots": parse_article(HTML)}}, "pins": {}}


class Verify(unittest.TestCase):
    def test_parse_only_adjacent_address_belongs_to_coord(self):
        spots = parse_article(HTML)
        self.assertEqual([s["name"] for s in spots], ["", "六郷土手河川敷公園", ""])
        self.assertEqual(spots[2]["address"], "")

    def test_article_id_both_blog_domains(self):
        self.assertEqual("58499744", article_id("http://blog.livedoor.jp/fumichen2/archives/58499744.html"))
        self.assertEqual("60086133", article_id("https://fumichen2.livedoor.blog/archives/60086133.html"))
        self.assertIsNone(article_id("https://example.com/archives/1.html"))

    def test_ok_and_drift(self):
        self.assertEqual(check_scene(scene(), snap())["status"], "ok")
        r = check_scene(scene(lat=35.5438, lng=139.7223), snap())
        self.assertEqual(r["status"], "drift")
        self.assertGreater(r["dist"], 15)

    def test_override_needs_reason(self):
        self.assertEqual(check_scene(scene(lat=35.55, coord_override="fumi typo"), snap())["status"], "override")

    def test_unverified_without_name_match(self):
        self.assertEqual(check_scene(scene(name="別の場所", address="", lat=35.0), snap())["status"], "unverified")

    def test_pin_survives_rename(self):
        s = snap()
        update_pins(s, [check_scene(scene(), s) | {"id": "a"}])
        self.assertEqual(check_scene(scene(name="改名後", address="", lat=35.6), s)["status"], "drift")

    def test_substring_name_is_not_a_match(self):
        self.assertEqual(match_spots({"name": "六郷", "address": ""}, parse_article(HTML)), [])

    def test_sanity_and_guard(self):
        self.assertTrue(sanity([scene(lat=139.7, lng=35.5)]))
        guard([scene()], snap())
        with self.assertRaises(SystemExit):
            guard([scene(lat=35.55)], snap())


if __name__ == "__main__":
    unittest.main()
