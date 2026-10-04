#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_yamakawa_ui as pub  # noqa: E402

R2 = pub.R2


def feat(fid, **props):
    p = {"id": fid, "name": fid, "category": "Blog・MSG", "subcategory": "ブログ写真・グリーティング", "sceneTitle": "t",
         "sceneNote": "n", "sourceLabel": "s", "sourceUrl": "", "referenceUrl": "", "tags": ["山川宇衣"], "images": []}
    p.update(props)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [139.0, 35.0]}, "properties": p}


class CarryReview(unittest.TestCase):
    def test_keeps_reviewed_state_and_confirms_new_points(self):
        reviewed = {"classification": {"category": "x", "subcategory": "y", "method": "manual-review", "status": "confirmed"},
                    "classificationCandidates": {"members": ["山川宇衣"], "projects": [], "contentTypes": ["MSG"]}}
        built = {"features": [feat("old"), feat("fresh"), feat("legacy")]}
        published = {"features": [feat("old", **reviewed), feat("legacy")]}
        kept, new = pub.carry_review(built, published, {"fresh": {"content_type": "ラジオ番組"}})
        by = {f["properties"]["id"]: f["properties"] for f in built["features"]}
        self.assertEqual((kept, new), (1, 1))
        self.assertEqual(by["old"]["classification"]["status"], "confirmed")
        self.assertEqual(by["old"]["classificationCandidates"]["contentTypes"], ["MSG"])
        self.assertEqual(by["fresh"]["classification"]["method"], "manual-review")
        self.assertEqual(by["fresh"]["classificationCandidates"]["contentTypes"], ["ラジオ番組"])
        self.assertNotIn("classification", by["legacy"])  # left to migrate(): legacy-import / unreviewed


class CarryCrawled(unittest.TestCase):
    def test_keeps_cron_appended_points_scenes_do_not_have(self):
        built = {"features": [feat("hand")]}
        published = {"features": [feat("hand"), feat("fumi-article:abc"), feat("dropped-hand-point")]}
        self.assertEqual(pub.carry_crawled(built, published), 1)
        self.assertEqual([f["properties"]["id"] for f in built["features"]], ["hand", "fumi-article:abc"])


class PublicCopy(unittest.TestCase):
    def test_rewrites_wording_images_and_source(self):
        f = feat("msg-1", images=[f"{R2}/yamakawa-ui/manual/spot/01_original.png"])
        out = pub.public_feature(f, {"category": "番組・イベント", "subcategory": "TALK ABOUT", "scene_title": "TALK ABOUT 紹介地",
                                     "scene_note": "ラジオで紹介された場所", "source_label": "TBSラジオ「TALK ABOUT」"})["properties"]
        self.assertEqual(out["images"], [f"{R2}/seichi/yamakawa-ui/spot/01_original.png"])
        self.assertEqual(out["source"]["tags"], ["山川宇衣", "TALK ABOUT"])
        self.assertEqual(out["classification"]["status"], "confirmed")
        self.assertEqual((out["members"], out["sourceKey"]), (["山川宇衣"], "msg-1"))
        self.assertEqual(f["properties"]["category"], "Blog・MSG")  # the 山川宇衣 map keeps its own wording

    def test_refuses_what_saka46log_would_drop(self):
        with self.assertRaisesRegex(ValueError, "MSG"):
            pub.public_feature(feat("a", sceneNote="メッセージに添付された写真"), {})
        with self.assertRaisesRegex(ValueError, "/seichi/"):
            pub.public_feature(feat("b", images=["https://example.com/x.jpg"]), {})

    def test_upsert_adds_updates_and_is_idempotent(self):
        all_map = {"features": [feat("keep"), feat("x", sceneNote="old")]}
        copies = [feat("x", sceneNote="new"), feat("y")]
        self.assertEqual(pub.upsert_public(all_map, copies), (1, 1))
        self.assertEqual(pub.upsert_public(all_map, copies), (0, 0))
        self.assertEqual([f["properties"]["id"] for f in all_map["features"]], ["keep", "x", "y"])


if __name__ == "__main__":
    unittest.main()
