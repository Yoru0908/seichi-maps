#!/usr/bin/env python3
"""同步公开 Google My Maps KML，并保留来源分类与增量状态。"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "mymaps_sources.json"
OVERRIDES_PATH = ROOT / "config" / "mymaps_overrides.json"
DEFAULT_STATE_DIR = ROOT / ".tmp" / "mymaps-sync-state"
KML_NS = "http://www.opengis.net/kml/2.2"
NS = {"k": KML_NS}
IMAGE_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
URL_IMAGE_RE = re.compile(
    r"https?://[^\s\"'<>]+\.(?:jpe?g|png|gif|webp)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise ValueError(f"Invalid source config: {path}")
    return value


def load_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    return value.get("overrides", {}) if isinstance(value, dict) else {}


def apply_overrides(geojson: dict[str, Any], overrides: dict[str, Any]) -> None:
    for feature in geojson.get("features", []):
        source_key = feature["properties"].get("sourceKey")
        override = overrides.get(source_key)
        if not isinstance(override, dict):
            continue
        properties = feature["properties"]
        classification = properties.setdefault("classification", {})
        for field in ("category", "subcategory", "method", "status"):
            if field in override:
                classification[field] = override[field]
        if "category" in override:
            properties["category"] = override["category"]
        if "subcategory" in override:
            properties["subcategory"] = override["subcategory"]
        if "members" in override:
            properties["members"] = list(override["members"] or [])
            classification["method"] = "manual"
            classification["status"] = "reviewed"


def select_source(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    if args.source:
        for source in config["sources"]:
            if source.get("id") == args.source:
                return dict(source)
        raise ValueError(f"Unknown source id: {args.source}")
    if not args.map_id:
        raise ValueError("Specify --source or --map-id")
    return {
        "id": args.name or args.map_id,
        "label": args.name or args.map_id,
        "provider": args.name or "公开 Google My Maps",
        "mapId": args.map_id,
        "sourceUrl": f"https://www.google.com/maps/d/viewer?mid={args.map_id}",
        "platform": {},
    }


def fetch_kml(map_id: str, timeout: int) -> bytes:
    url = f"https://www.google.com/maps/d/kml?mid={map_id}&forcekml=1"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SakamichiTools My Maps Sync/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"KML request returned HTTP {response.status}")
            body = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"KML request returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"KML request failed: {error.reason}") from error
    if b"<kml" not in body[:4096].lower():
        preview = body[:160].decode("utf-8", errors="replace").replace("\n", " ")
        raise RuntimeError(f"Response is not KML; possible private/login page: {preview}")
    return body


def element_text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def child(element: ET.Element, name: str) -> ET.Element | None:
    return element.find(f"{{{KML_NS}}}{name}")


def child_text(element: ET.Element, name: str) -> str:
    return element_text(child(element, name))


def clean_description(value: str) -> str:
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_images(description: str) -> list[str]:
    value = html.unescape(description)
    urls = IMAGE_RE.findall(value)
    urls.extend(URL_IMAGE_RE.findall(value))
    return list(dict.fromkeys(urls))


def parse_point(placemark: ET.Element) -> tuple[float, float] | None:
    point = child(placemark, "Point")
    if point is None:
        return None
    coordinates = child_text(point, "coordinates")
    if not coordinates:
        return None
    first = coordinates.split()[0].split(",")
    if len(first) < 2:
        return None
    try:
        return float(first[1]), float(first[0])
    except ValueError:
        return None


def source_key(map_id: str, layer: str, name: str, coordinates: tuple[float, float]) -> str:
    identity = "|".join(
        [
            map_id,
            layer.strip(),
            name.strip(),
            f"{coordinates[0]:.5f},{coordinates[1]:.5f}",
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"mymaps:{map_id}:{digest}"


def feature_fingerprint(feature: dict[str, Any]) -> str:
    properties = feature["properties"]
    value = {
        "name": properties.get("name", ""),
        "description": properties.get("sceneNote", ""),
        "layer": properties.get("source", {}).get("layer", ""),
        "tags": properties.get("source", {}).get("tags", []),
        "imageCount": len(properties.get("images", [])),
        "stableImages": [
            url
            for url in properties.get("images", [])
            if "mymaps.usercontent.google.com" not in url
        ],
        "classification": properties.get("classification", {}),
        "members": properties.get("members", []),
        "coordinates": feature["geometry"]["coordinates"],
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def walk_placemarks(
    element: ET.Element,
    folder_path: list[str],
    source: dict[str, Any],
    features: list[dict[str, Any]],
    skipped: list[str],
) -> None:
    for item in list(element):
        local = item.tag.rsplit("}", 1)[-1]
        if local == "Folder":
            name = child_text(item, "name")
            next_path = folder_path + ([name] if name else [])
            walk_placemarks(item, next_path, source, features, skipped)
            continue
        if local != "Placemark":
            walk_placemarks(item, folder_path, source, features, skipped)
            continue
        name = child_text(item, "name") or "未命名地点"
        layer = "/".join(folder_path)
        coordinates = parse_point(item)
        if coordinates is None:
            skipped.append(f"{layer}/{name}".strip("/"))
            continue
        description = child_text(item, "description")
        source_id = source_key(source["mapId"], layer, name, coordinates)
        platform = source.get("platform") or {}
        category = platform.get("category") or layer or source.get("label", "")
        subcategory = platform.get("subcategory") or layer
        tags = list(source.get("tags") or [])
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coordinates[1], coordinates[0]],
            },
            "properties": {
                "id": source_id,
                "sourceKey": source_id,
                "name": name,
                "category": category,
                "subcategory": subcategory,
                "categoryColor": platform.get("categoryColor", "#666666"),
                "address": "",
                "sceneTitle": "",
                "sceneNote": clean_description(description),
                "sourceLabel": source.get("label", source.get("provider", "")),
                "sourceUrl": source.get("sourceUrl", ""),
                "referenceUrl": source.get("sourceUrl", ""),
                "tags": tags,
                "images": extract_images(description),
                "members": [],
                "source": {
                    "provider": source.get("provider", ""),
                    "url": source.get("sourceUrl", ""),
                    "mapId": source.get("mapId", ""),
                    "layer": layer,
                    "tags": tags,
                    "name": name,
                },
                "classification": {
                    "category": category,
                    "subcategory": subcategory,
                    "method": "manual" if platform else "source-layer",
                    "status": "reviewed" if platform else "unreviewed",
                },
                "classificationCandidates": {
                    "members": [],
                    "projects": [],
                    "contentTypes": [],
                },
            },
        }
        feature["properties"]["fingerprint"] = feature_fingerprint(feature)
        features.append(feature)


def parse_kml(body: bytes, source: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise RuntimeError(f"Invalid KML XML: {error}") from error
    features: list[dict[str, Any]] = []
    skipped: list[str] = []
    walk_placemarks(root, [], source, features, skipped)
    return {"type": "FeatureCollection", "features": features}, skipped


def diff_features(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    old = previous.get("features", {})
    new = {
        feature["properties"]["sourceKey"]: feature["properties"]["fingerprint"]
        for feature in current.get("features", [])
    }
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(key for key in set(new) & set(old) if new[key] != old[key])
    return {
        "added": added,
        "changed": changed,
        "removed": removed,
        "counts": {
            "added": len(added),
            "changed": len(changed),
            "removed": len(removed),
        },
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else ROOT.parent / path


def print_report(source: dict[str, Any], diff: dict[str, Any], skipped: list[str]) -> None:
    counts = diff["counts"]
    print(f"Source: {source.get('label', source.get('id'))}")
    print(f"Features: added={counts['added']} changed={counts['changed']} removed={counts['removed']}")
    if skipped:
        print(f"Skipped non-point placemarks: {len(skipped)}")
        for value in skipped[:10]:
            print(f"  - {value}")
    for label in ("added", "changed", "removed"):
        values = diff[label]
        if values:
            print(f"{label.title()} samples:")
            for value in values[:10]:
                print(f"  - {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="同步公开 Google My Maps KML 并生成 GeoJSON")
    parser.add_argument("--source", help="配置文件中的 source id")
    parser.add_argument("--map-id", help="公开 Google My Maps 的 mid")
    parser.add_argument("--name", help="一次性 source 的显示名称")
    parser.add_argument("--output", help="GeoJSON 输出路径")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="source 配置 JSON")
    parser.add_argument("--state-dir", help="增量状态目录")
    parser.add_argument("--overrides", help="人工 overrides JSON")
    parser.add_argument("--raw-dir", help="原始 KML 保存目录")
    parser.add_argument("--save-raw", action="store_true", help="保存原始 KML 快照")
    parser.add_argument("--dry-run", action="store_true", help="只抓取和生成 diff，不写 output/state")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时时间（秒）")
    args = parser.parse_args()

    try:
        config = load_config(Path(args.config))
        source = select_source(args, config)
        output = resolve_path(args.output or source.get("output"), ROOT / ".tmp" / "mymaps-sync" / f"{source['id']}.geojson")
        state_dir = resolve_path(args.state_dir, DEFAULT_STATE_DIR)
        state_path = state_dir / f"{source['id']}.json"
        body = fetch_kml(source["mapId"], args.timeout)
        if args.save_raw:
            raw_dir = resolve_path(args.raw_dir, ROOT / ".tmp" / "mymaps-raw")
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{source['id']}.kml").write_bytes(body)
        current, skipped = parse_kml(body, source)
        overrides_path = Path(args.overrides) if args.overrides else OVERRIDES_PATH
        apply_overrides(current, load_overrides(overrides_path))
        for feature in current["features"]:
            feature["properties"]["fingerprint"] = feature_fingerprint(feature)
        previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        diff = diff_features(previous, current)
        print_report(source, diff, skipped)
        if args.dry_run:
            return 0
        atomic_write_json(output, current)
        state = {
            "sourceId": source["id"],
            "mapId": source["mapId"],
            "featureCount": len(current["features"]),
            "features": {
                feature["properties"]["sourceKey"]: feature["properties"]["fingerprint"]
                for feature in current["features"]
            },
        }
        atomic_write_json(state_path, state)
        print(f"Wrote: {output}")
        print(f"State: {state_path}")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"sync_mymaps_sources.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
