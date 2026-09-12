import copy
import json
import sys
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sync_mymaps_sources import diff_features, parse_kml, source_key


SOURCE = {
    "id": "fixture",
    "label": "Fixture Map",
    "provider": "Fixture Author",
    "mapId": "fixture-map",
    "sourceUrl": "https://example.test/map",
    "platform": {
        "category": "櫻坂46",
        "subcategory": "Fixture",
        "categoryColor": "#ff00aa",
    },
}

KML = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>シングル・アルバム</name>
      <Folder>
        <name>MV</name>
        <Placemark>
          <name>テスト地点</name>
          <description><![CDATA[<p>説明</p><img src="https://img.test/a.jpg">]]></description>
          <Point><coordinates>139.700000,35.600000,0</coordinates></Point>
        </Placemark>
        <Placemark>
          <name>線形地点</name>
          <LineString><coordinates>139.7,35.6,0 139.8,35.7,0</coordinates></LineString>
        </Placemark>
      </Folder>
    </Folder>
  </Document>
</kml>'''.encode('utf-8')


class SyncMyMapsTests(unittest.TestCase):
    def test_nested_layer_point_and_source_metadata(self):
        geojson, skipped = parse_kml(KML, SOURCE)
        self.assertEqual(len(geojson["features"]), 1)
        self.assertEqual(skipped, ["シングル・アルバム/MV/線形地点"])
        properties = geojson["features"][0]["properties"]
        self.assertEqual(properties["source"]["layer"], "シングル・アルバム/MV")
        self.assertEqual(properties["classification"]["category"], "櫻坂46")
        self.assertEqual(properties["members"], [])
        self.assertEqual(properties["images"], ["https://img.test/a.jpg"])
        self.assertEqual(properties["sceneNote"], "説明")

    def test_source_key_uses_identity_only(self):
        first = source_key("map", "Layer", "Name", (35.6, 139.7))
        second = source_key("map", "Layer", "Name", (35.6, 139.7))
        changed_name = source_key("map", "Layer", "Other", (35.6, 139.7))
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed_name)

    def test_diff_added_changed_removed(self):
        old, _ = parse_kml(KML, SOURCE)
        current = copy.deepcopy(old)
        current["features"][0]["properties"]["sceneNote"] = "更新后的说明"
        current["features"][0]["properties"]["fingerprint"] = "changed"
        current["features"].append(copy.deepcopy(old["features"][0]))
        current["features"][-1]["properties"]["sourceKey"] = "new-key"
        current["features"][-1]["properties"]["fingerprint"] = "new"
        previous = {
            "features": {
                old["features"][0]["properties"]["sourceKey"]: old["features"][0]["properties"]["fingerprint"],
                "removed-key": "removed",
            }
        }
        result = diff_features(previous, current)
        self.assertEqual(result["counts"], {"added": 1, "changed": 1, "removed": 1})


if __name__ == "__main__":
    unittest.main()
