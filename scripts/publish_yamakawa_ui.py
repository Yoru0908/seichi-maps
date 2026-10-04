#!/usr/bin/env python3
"""山川宇衣地图 → sakamichi-platform 分支的 public/seichi（网站发布用）。

解决 维护文档/runbook/seichi-map-publish.md 的两个问题：
  #2 build_geojson.py 每次整份重建，文件里没有审核字段 → 覆盖后人工审核（confirmed）全部丢失。
     这里按 id 从「当前已发布的版本」继承 classification / classificationCandidates；新点记为人工确认。
  #3 综合图 sakurazaka-all.geojson 里的「干净副本」原来要手写。
     这里由 scene 的 `public_copy` 字段生成（有该字段 = 导出；里面只写需要改写的项），
     并按 坂ログ worker/seichi.ts 的规则预检：含 MSG/メッセージ/msg-archive 的点会被坂ログ 整条丢弃 → 直接报错。
  #4 Homeserver 的 fumi cron（sakamichi-platform scripts/seichi/append_member_spots.py）会把她新文章的点
     （id 以 fumi-article: 开头）追加进已发布的 yamakawa-ui.geojson。scenes 里没有这些点，重建时原样保留在末尾；
     若某篇文章后来在 scenes 里手工收录了，删掉对应的 fumi-article: 点即可（见 carry_crawled）。

用法（在 sakamichi-platform 分支的 worktree 上）：
  python3 scripts/publish_yamakawa_ui.py --platform-dir <worktree>/public/seichi [--dry-run] [--no-build]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "yamakawa-ui" / "yamakawa-ui-scenes.json"
BUILT = ROOT / "yamakawa-ui" / "geojson" / "yamakawa-ui.geojson"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_seichi_metadata import atomic_write, migrate  # noqa: E402

MEMBER = "山川宇衣"
GROUP = "櫻坂46"
R2 = "https://pub-6d7574c4452b41519ab8adf1541d7f9e.r2.dev"
# Mirrors 坂ログ worker/seichi.ts sanitizeFeatures(): these fields must not mention private messages.
BLOCKED = re.compile(r"\bMSG\b|メッセージ|msg-archive", re.I)
PUBLIC_FIELDS = {  # public_copy key → GeoJSON property
    "category": "category", "subcategory": "subcategory", "category_color": "categoryColor",
    "scene_title": "sceneTitle", "scene_note": "sceneNote", "source_label": "sourceLabel",
    "source_url": "sourceUrl", "reference_url": "referenceUrl", "tags": "tags",
}
REVIEW_KEYS = ("classification", "classificationCandidates")


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as h:
        return json.load(h)


def carry_review(built: dict, published: dict, scenes: dict[str, dict]) -> tuple[int, int]:
    """#2: keep reviewed state by id; features new since the last publish are hand-added → confirmed."""
    old = {f["properties"].get("id"): f["properties"] for f in published.get("features", [])}
    kept = new = 0
    for f in built["features"]:
        p = f["properties"]
        prev = old.get(p["id"])
        if prev and all(k in prev for k in REVIEW_KEYS):
            for k in REVIEW_KEYS:
                p[k] = copy.deepcopy(prev[k])
            kept += 1
        elif prev is None:
            scene = scenes.get(p["id"], {})
            p["classification"] = {"category": p["category"], "subcategory": p["subcategory"], "method": "manual-review", "status": "confirmed"}
            p["classificationCandidates"] = {"members": [MEMBER], "projects": [], "contentTypes": [scene["content_type"]] if scene.get("content_type") else []}
            new += 1
    return kept, new


def carry_crawled(built: dict, published: dict) -> int:
    """#4: keep the cron-appended fumi-article: points that scenes.json does not have."""
    ids = {f["properties"]["id"] for f in built["features"]}
    crawled = [f for f in published.get("features", [])
               if str(f["properties"].get("id", "")).startswith("fumi-article:") and f["properties"]["id"] not in ids]
    built["features"].extend(copy.deepcopy(crawled))
    return len(crawled)


def public_feature(yui_feature: dict, public_copy: dict) -> dict:
    """#3: the 综合图 copy of one 山川宇衣 point, with its public-source wording."""
    f = copy.deepcopy(yui_feature)
    p = f["properties"]
    for key, prop in PUBLIC_FIELDS.items():
        if key in public_copy:
            p[prop] = copy.deepcopy(public_copy[key])
    p["images"] = [u.replace(f"{R2}/yamakawa-ui/manual/", f"{R2}/seichi/yamakawa-ui/") for u in p.get("images", [])]
    p["members"] = [MEMBER]
    p["sourceKey"] = p["id"]
    p["source"] = {"group": GROUP, "provider": p.get("sourceLabel", ""), "url": p.get("sourceUrl", ""), "mapId": "",
                   "layer": p["category"], "tags": [MEMBER, p["subcategory"]], "name": p["name"]}
    p["classification"] = {"category": p["category"], "subcategory": p["subcategory"], "method": "manual-review", "status": "confirmed"}
    cand = yui_feature["properties"].get("classificationCandidates") or {}
    p["classificationCandidates"] = {"members": [MEMBER], "projects": list(cand.get("projects", [])),
                                     "contentTypes": [c for c in cand.get("contentTypes", []) if not BLOCKED.search(c)]}
    problems = check_public(p)
    if problems:
        raise ValueError(f"{p['id']}: {'; '.join(problems)}（改 scene 的 public_copy）")
    return f


def check_public(p: dict) -> list[str]:
    problems = []
    text = " ".join(str(p.get(k) or "") for k in ("sceneTitle", "sceneNote", "sourceLabel", "sourceUrl", "referenceUrl"))
    if BLOCKED.search(text):
        problems.append("标题/说明/出处含 MSG・メッセージ，坂ログ 会整条丢弃")
    bad = [u for u in p.get("images", []) if not u.startswith(f"{R2}/seichi/")]
    if bad:
        problems.append(f"图片不在 R2 /seichi/ 前缀下，坂ログ 不显示：{bad[:2]}")
    return problems


def upsert_public(all_map: dict, copies: list[dict]) -> tuple[int, int]:
    index = {f["properties"].get("id"): i for i, f in enumerate(all_map["features"])}
    added = updated = 0
    for f in copies:
        i = index.get(f["properties"]["id"])
        if i is None:
            all_map["features"].append(f)
            added += 1
        elif all_map["features"][i] != f:
            all_map["features"][i] = f
            updated += 1
    return added, updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--platform-dir", required=True, type=Path, help="sakamichi-platform 分支 worktree 的 public/seichi")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-build", action="store_true", help="跳过 build_geojson.py（已手动生成时）")
    a = ap.parse_args()
    if not a.no_build:
        subprocess.run([sys.executable, str(ROOT / "yamakawa-ui" / "build_geojson.py")], check=True, stdout=subprocess.DEVNULL)
    yui_path, all_path = a.platform_dir / "yamakawa-ui.geojson", a.platform_dir / "sakurazaka-all.geojson"
    scenes = {s["id"]: s for s in load(SCENES)["scenes"]}
    built, published, all_map = load(BUILT), load(yui_path), load(all_path)

    # migrate() first (it appends source/classification/candidates in its own key order), then overwrite the
    # review values in place — same key order as the published file, so git diffs show only real changes.
    tmp = yui_path.with_suffix(".publish.tmp")
    atomic_write(tmp, built)
    migrate(tmp, dry_run=False)
    built = load(tmp)
    tmp.unlink()
    kept, new = carry_review(built, published, scenes)
    crawled = carry_crawled(built, published)
    by_id = {f["properties"]["id"]: f for f in built["features"]}
    copies = [public_feature(by_id[sid], s["public_copy"]) for sid, s in scenes.items() if "public_copy" in s and sid in by_id]
    added, updated = upsert_public(all_map, copies)

    reviewed = sum(1 for f in built["features"] if f["properties"]["classification"].get("status") == "confirmed")
    print(f"yamakawa-ui: {len(built['features'])} 点｜继承审核 {kept}｜新点 {new}｜已确认 {reviewed}｜保留爬取 {crawled}")
    print(f"sakurazaka-all: {len(all_map['features'])} 点｜公开副本 {len(copies)}（新增 {added}，更新 {updated}）")
    if a.dry_run:
        print("dry-run：未写入")
        return 0
    atomic_write(yui_path, built)
    atomic_write(all_path, all_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
