#!/usr/bin/env python3
"""为现有 GeoJSON 添加来源与平台分类字段，并清除未经验证的成员标签。"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_FILES = [
    "fumi-sakurazaka.geojson",
    "sakurazaka-all.geojson",
    "keyakizaka-all.geojson",
    "keyaki-hiragana.geojson",
    "hinatazaka-all.geojson",
    "tokyo10sha.geojson",
    "oversea.geojson",
    "yamakawa-ui.geojson",
]
CLEAR_MEMBER_FILES = {
    "fumi-sakurazaka.geojson",
    "sakurazaka-all.geojson",
    "keyakizaka-all.geojson",
    "keyaki-hiragana.geojson",
}


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def migrate(path: Path, dry_run: bool) -> tuple[int, int]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    changed = 0
    cleared_members = 0
    for feature in data.get("features", []):
        properties = feature.setdefault("properties", {})
        original_tags = list(properties.get("tags") or [])
        provider = properties.get("sourceLabel", "") or ""
        source_url = properties.get("sourceUrl", "") or properties.get("referenceUrl", "") or ""
        layer = properties.get("sourceLayer", "") or properties.get("category", "") or ""
        source = properties.get("source") or {
            "provider": provider,
            "url": source_url,
            "mapId": properties.get("sourceMapId", "") or "",
            "layer": layer,
            "tags": original_tags,
            "name": properties.get("name", "") or "",
        }
        classification = properties.get("classification") or {
            "category": properties.get("category", "") or "",
            "subcategory": properties.get("subcategory", "") or "",
            "method": "legacy-import",
            "status": "unreviewed",
        }
        candidates = properties.get("classificationCandidates") or {
            "members": [],
            "projects": [],
            "contentTypes": [],
        }
        before = json.dumps(properties, ensure_ascii=False, sort_keys=True)
        properties["source"] = source
        properties["classification"] = classification
        properties["classificationCandidates"] = candidates
        if path.name in CLEAR_MEMBER_FILES and properties.get("members"):
            properties["members"] = []
            cleared_members += 1
        else:
            properties.setdefault("members", [])
        after = json.dumps(properties, ensure_ascii=False, sort_keys=True)
        if before != after:
            changed += 1
    if not dry_run:
        atomic_write(path, data)
    return changed, cleared_members


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移圣巡 GeoJSON 来源字段并清理错误 members")
    parser.add_argument("--public-dir", required=True, help="sakamichi-platform/public/seichi 目录")
    parser.add_argument("--file", action="append", dest="files", help="只处理指定文件，可重复")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    public_dir = Path(args.public_dir)
    files = args.files or DEFAULT_FILES
    for filename in files:
        path = public_dir / filename
        if not path.exists():
            print(f"SKIP {filename}: not found")
            continue
        changed, cleared = migrate(path, args.dry_run)
        action = "would update" if args.dry_run else "updated"
        print(f"{action} {filename}: features={changed}, cleared_members={cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
