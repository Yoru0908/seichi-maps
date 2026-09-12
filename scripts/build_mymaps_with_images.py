#!/usr/bin/env python3
"""Build Google My Maps imports with fumi article image links.

The normal My Maps CSV importer does not create attached marker photos.
This script keeps the reliable CSV layer workflow, then adds image URL
columns and image-rich KML descriptions generated from cached fumi HTML.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup


CSV_COLUMNS = [
    "Name",
    "Location",
    "Layer",
    "Category",
    "Scene",
    "Scene Ref",
    "Scene Note",
    "Image Links",
    "Image Preview",
    "Source URL",
    "Source Label",
    "Reference URL",
    "Confidence",
    "Access Note",
    "Tags",
    "Google Maps URL",
]

CATEGORY_COLORS = {
    "scene": "ff2f5597",
    "transit": "ff666666",
    "shop": "ffb45f06",
    "restaurant": "ff00a65a",
    "viewpoint": "ff7030a0",
    "event": "ffcc0000",
    "shrine": "ff38761d",
    "park": "ff6aa84f",
    "station": "ff666666",
    "hotel": "ff3c78d8",
    "other": "ff990000",
}

GROUP_LAYER_ORDER = [
    "四期生デビューVlog仙台松島",
    "Youtube",
    "四期生合宿_山中湖",
    "個人PV",
    "光源MV",
    "四期生MVそこさく収録",
    "MSG&雑誌&Blog",
]


@dataclass
class ArticleImage:
    full: str
    thumb: str
    alt: str = ""


@dataclass
class ArticleBlock:
    article_id: str
    index: int
    images: list[ArticleImage]
    text: str


@dataclass
class ImageMatch:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    block: ArticleBlock | None = None
    images: list[ArticleImage] = field(default_factory=list)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate My Maps layer imports with article image links.")
    parser.add_argument("--scenes", required=True, type=Path, help="Scene JSON file")
    parser.add_argument("--articles-dir", required=True, type=Path, help="Directory containing cached fumi article HTML files")
    parser.add_argument("--extra-article", action="append", default=[], type=Path, help="Additional cached fumi HTML file")
    parser.add_argument("--output", required=True, type=Path, help="Output directory")
    parser.add_argument("--title", default="山川宇衣 巡礼マップ合集", help="KML title")
    parser.add_argument("--compact", action="store_true", help="Use compact My Maps descriptions")
    parser.add_argument("--group-layers", action="store_true", help="Merge source layers into practical My Maps groups")
    parser.add_argument("--r2-map", type=Path, help="JSON map from original/local image URLs to mirrored R2 URLs")
    args = parser.parse_args()

    scene_data = json.loads(args.scenes.read_text(encoding="utf-8"))
    scenes = scene_data.get("scenes", [])
    if not scenes:
        raise SystemExit("No scenes found.")

    article_blocks = load_article_blocks(args.articles_dir, args.extra_article)
    image_url_map = load_image_url_map(args.r2_map)

    args.output.mkdir(parents=True, exist_ok=True)
    csv_dir = args.output / "mymaps-import-with-images"
    kml_dir = args.output / "kml-with-images"
    csv_dir.mkdir(exist_ok=True)
    kml_dir.mkdir(exist_ok=True)

    enriched: list[dict[str, Any]] = []
    match_rows: list[dict[str, str]] = []
    for scene in scenes:
        match = match_scene(scene, article_blocks)
        scene_copy = dict(scene)
        if args.group_layers:
            scene_copy["source_layer"] = clean_text(scene_copy.get("layer"))
            scene_copy["layer"] = grouped_layer(scene_copy)
        match.images = remap_images(scene_images(scene_copy, match), image_url_map)
        scene_copy["_image_match"] = match
        enriched.append(scene_copy)
        match_rows.append(match_report_row(scene, match))

    layer_order = ordered_layers(enriched)
    layer_filenames = build_layer_filenames(layer_order)

    for idx, layer in enumerate(layer_order, start=1):
        layer_scenes = [scene for scene in enriched if clean_text(scene.get("layer")) == layer]
        stem = layer_filenames[layer]
        filename = f"{stem}.csv"
        write_csv(csv_dir / filename, layer_scenes)
        write_kml(kml_dir / f"{stem}.kml", layer, layer_scenes, compact=args.compact)

    write_kml(args.output / "yamakawa-ui-all_with_images.kml", args.title, enriched, compact=args.compact)
    write_match_report(args.output / "image-match-report.csv", match_rows)
    write_readme(args.output / "KML_IMPORT_GUIDE.md", layer_order, layer_filenames)
    write_readme(args.output / "README_IMPORT_IMAGES.md", layer_order, layer_filenames)

    matched = sum(1 for row in match_rows if row["matched"] == "yes")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "scenes": len(scenes),
                "matched_with_images": matched,
                "unmatched": len(scenes) - matched,
                "csv_dir": str(csv_dir),
                "kml_dir": str(kml_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def load_article_blocks(articles_dir: Path, extra_articles: list[Path]) -> dict[str, list[ArticleBlock]]:
    html_paths = list(articles_dir.glob("*.html")) + list(extra_articles)
    blocks_by_article: dict[str, list[ArticleBlock]] = {}
    for path in html_paths:
        article_id = article_id_from_text(path.name) or article_id_from_html(path)
        if not article_id:
            continue
        blocks = parse_article_blocks(path, article_id)
        blocks_by_article[article_id] = blocks
    return blocks_by_article


def parse_article_blocks(path: Path, article_id: str) -> list[ArticleBlock]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    body = soup.select_one(".article-body-inner") or soup.select_one(".article-body.entry-content")
    if not body:
        return []

    blocks: list[ArticleBlock] = []
    current_images: list[ArticleImage] = []
    current_texts: list[str] = []

    def flush() -> None:
        nonlocal current_images, current_texts
        if current_images:
            blocks.append(
                ArticleBlock(
                    article_id=article_id,
                    index=len(blocks) + 1,
                    images=current_images,
                    text=normalize_space(" ".join(current_texts)),
                )
            )
        current_images = []
        current_texts = []

    for child in body.find_all(["div", "p"], recursive=False):
        images = []
        for img in child.find_all("img"):
            src = clean_text(img.get("src"))
            if "livedoor.blogimg.jp/fumichen2" not in src:
                continue
            full = src
            parent = img.parent
            if parent and getattr(parent, "name", None) == "a":
                href = clean_text(parent.get("href"))
                if href.startswith("http"):
                    full = href
            images.append(ArticleImage(full=full, thumb=src, alt=clean_text(img.get("alt") or img.get("title"))))

        text = normalize_space(child.get_text(" ", strip=True))
        if images:
            flush()
            current_images = images
            if text:
                current_texts.append(text)
        elif current_images and text:
            current_texts.append(text)

    flush()
    return blocks


def load_image_url_map(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {clean_text(row.get("source")): clean_text(row.get("url")) for row in data.get("images", []) if row.get("source") and row.get("url")}


def scene_images(scene: dict[str, Any], match: ImageMatch) -> list[ArticleImage]:
    images: list[ArticleImage] = []
    for item in scene.get("manual_images", []) or []:
        full = clean_text(item.get("full"))
        thumb = clean_text(item.get("thumb")) or full
        if full:
            images.append(ArticleImage(full=full, thumb=thumb, alt=clean_text(item.get("label"))))
    images.extend(match.images)
    return images


def remap_images(images: list[ArticleImage], image_url_map: dict[str, str]) -> list[ArticleImage]:
    if not image_url_map:
        return images
    remapped = []
    for image in images:
        remapped.append(
            ArticleImage(
                full=image_url_map.get(image.full, image.full),
                thumb=image_url_map.get(image.thumb, image.thumb),
                alt=image.alt,
            )
        )
    return remapped


def match_scene(scene: dict[str, Any], blocks_by_article: dict[str, list[ArticleBlock]]) -> ImageMatch:
    source_article = article_id_from_text(clean_text(scene.get("source_url")))
    blocks = blocks_by_article.get(source_article or "", [])
    best = ImageMatch()
    for block in blocks:
        score, reasons = score_scene_block(scene, block)
        if score > best.score:
            best = ImageMatch(score=score, reasons=reasons, block=block, images=block.images)

    if best.score >= 30 or ("reference_url" in best.reasons and best.score >= 18):
        return best
    return ImageMatch(score=best.score, reasons=best.reasons, block=best.block, images=[])


def score_scene_block(scene: dict[str, Any], block: ArticleBlock) -> tuple[int, list[str]]:
    text = block.text
    compact_text = compact_match_text(text)
    score = 0
    reasons: list[str] = []

    if coordinates_match(scene, text):
        score += 100
        reasons.append("coord")

    for key, weight in [("scene_title", 120), ("name", 60)]:
        value = compact_match_text(clean_text(scene.get(key)))
        if len(value) >= 4 and value in compact_text:
            score += weight
            reasons.append(f"compact:{key}")

    for key, weight in [("name", 45), ("scene_title", 60), ("address", 15), ("reference_url", 15)]:
        value = normalize_space(clean_text(scene.get(key)))
        if value and value in text:
            score += weight
            reasons.append(key)

    generic_tokens = generic_scene_tokens(scene)
    meaningful_hits = 0
    for token in text_tokens(clean_text(scene.get("name")) + " " + clean_text(scene.get("scene_title"))):
        if token in text:
            if token in generic_tokens:
                score += 3
            else:
                score += 12
                meaningful_hits += 1
            reasons.append(f"token:{token}")

    if meaningful_hits >= 2:
        score += 35
        reasons.append("multi-token")

    return score, reasons


def coordinates_match(scene: dict[str, Any], text: str) -> bool:
    lat = scene.get("lat")
    lng = scene.get("lng")
    if lat in (None, "") or lng in (None, ""):
        return False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return False
    variants = [
        f"{lat_f:.7f}, {lng_f:.7f}",
        f"{lat_f:.7f},{lng_f:.7f}",
        f"{lat_f:.6f}, {lng_f:.6f}",
        f"{lat_f:.6f},{lng_f:.6f}",
        f"{lat_f:.5f}, {lng_f:.5f}",
        f"{lat_f:.5f},{lng_f:.5f}",
    ]
    return any(variant in text for variant in variants)


def text_tokens(value: str) -> list[str]:
    tokens = []
    seen = set()
    for token in re.split(r"[\s/・\-－()（）,、。:：]+", value):
        token = token.strip()
        if len(token) < 3 or token in seen or token.isdigit():
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def generic_scene_tokens(scene: dict[str, Any]) -> set[str]:
    name = clean_text(scene.get("name"))
    scene_title = clean_text(scene.get("scene_title"))
    title_tokens = set(text_tokens(scene_title))
    return {token for token in text_tokens(name) if token not in title_tokens}


def compact_match_text(value: str) -> str:
    return re.sub(r"[\s/・\-－()（）,、。:：]+", "", value or "")


def write_csv(path: Path, scenes: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for scene in scenes:
            writer.writerow(csv_row(scene))


def csv_row(scene: dict[str, Any]) -> dict[str, str]:
    match: ImageMatch = scene["_image_match"]
    return {
        "Name": clean_text(scene.get("name")),
        "Location": location_value(scene),
        "Layer": clean_text(scene.get("layer")),
        "Category": clean_text(scene.get("category")) or "Scene",
        "Scene": clean_text(scene.get("scene_title")),
        "Scene Ref": clean_text(scene.get("scene_ref")),
        "Scene Note": clean_text(scene.get("scene_note")),
        "Image Links": image_links(match.images),
        "Image Preview": match.images[0].thumb if match.images else "",
        "Source URL": clean_text(scene.get("source_url")),
        "Source Label": clean_text(scene.get("source_label")),
        "Reference URL": clean_text(scene.get("reference_url")),
        "Confidence": clean_text(scene.get("confidence")),
        "Access Note": clean_text(scene.get("access_note")),
        "Tags": "; ".join(clean_text(tag) for tag in scene.get("tags", []) if clean_text(tag)),
        "Google Maps URL": google_maps_url(scene),
    }


def write_kml(path: Path, title: str, scenes: list[dict[str, Any]], compact: bool = False) -> None:
    layers: dict[str, list[dict[str, Any]]] = {}
    for scene in scenes:
        layers.setdefault(clean_text(scene.get("layer")) or "Unsorted", []).append(scene)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        f"<name>{xml(title)}</name>",
        *kml_styles(),
    ]
    for layer, layer_scenes in layers.items():
        coordinate_count = sum(
            bool(clean_text(scene.get("lat")) and clean_text(scene.get("lng")))
            for scene in layer_scenes
        )
        if coordinate_count == len(layer_scenes):
            location_mode = "point"
        elif coordinate_count:
            location_mode = "mixed"
        else:
            location_mode = "address"
        parts.append("<Folder>")
        parts.append(f"<name>{xml(layer)}</name>")
        for scene in layer_scenes:
            parts.append(
                kml_placemark(scene, compact=compact, location_mode=location_mode)
            )
        parts.append("</Folder>")
    parts.extend(["</Document>", "</kml>"])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def kml_styles() -> list[str]:
    styles = []
    for key, color in CATEGORY_COLORS.items():
        styles.append(
            "\n".join(
                [
                    f'<Style id="{key}">',
                    "<IconStyle>",
                    f"<color>{color}</color>",
                    "<scale>1.1</scale>",
                    "<Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href></Icon>",
                    "</IconStyle>",
                    "</Style>",
                ]
            )
        )
    return styles


def kml_placemark(
    scene: dict[str, Any],
    compact: bool = False,
    location_mode: str = "address",
) -> str:
    parts = [
        "<Placemark>",
        f"<name>{xml(scene.get('name'))}</name>",
        f"<styleUrl>#{style_id(scene)}</styleUrl>",
        f"<description><![CDATA[{description_html(scene, compact=compact)}]]></description>",
    ]
    if not compact:
        parts.append(extended_data(scene))
    lat = clean_text(scene.get("lat"))
    lng = clean_text(scene.get("lng"))
    address = clean_text(scene.get("address"))
    if address and not (lat and lng):
        # Coordinates are already provided by <Point>. Repeating them in
        # <address> makes My Maps geocode the coordinate string again and can
        # reject an otherwise valid row in a mixed address/coordinate layer.
        parts.append(f"<address>{xml(address)}</address>")
    if lat and lng:
        parts.append(f"<Point><coordinates>{xml(lng)},{xml(lat)},0</coordinates></Point>")
    parts.append("</Placemark>")
    return "\n".join(parts)


def description_html(scene: dict[str, Any], compact: bool = False) -> str:
    match: ImageMatch = scene["_image_match"]
    parts = ['<div style="font-family:Arial,sans-serif;max-width:520px">']
    if match.images:
        max_images = 4 if not compact else 2
        for image in match.images[:max_images]:
            parts.append(
                f'<img src="{html.escape(image.thumb)}" alt="{html.escape(image.alt)}" '
                'height="200" width="auto" />'
            )
    if compact:
        title = compact_title(scene)
        note = compact_note(scene)
        if title:
            parts.append(f"<p><b>{html.escape(title)}</b></p>")
        if note and note != title:
            parts.append(f"<p>{html.escape(note)}</p>")
        address = clean_text(scene.get("address"))
        if address:
            parts.append(f"<p><b>住所:</b> {html.escape(address)}</p>")
        confidence = clean_text(scene.get("confidence"))
        if confidence in {"unverified", "needs-review"}:
            parts.append("<p><b>確認:</b> 要確認</p>")
    else:
        for label, value in [
            ("Scene", scene.get("scene_title")),
            ("Scene ref", scene.get("scene_ref")),
            ("Scene note", scene.get("scene_note")),
            ("Confidence", scene.get("confidence")),
            ("Access note", scene.get("access_note")),
            ("Address", scene.get("address")),
        ]:
            text = clean_text(value)
            if text:
                parts.append(f"<p><b>{html.escape(label)}:</b> {html.escape(text)}</p>")
    if match.images and not compact:
        links = "<br>".join(
            f'<a href="{html.escape(image.full)}">Image {idx}</a>' for idx, image in enumerate(match.images, start=1)
        )
        parts.append(f"<p><b>Images:</b><br>{links}</p>")
    source_url = clean_text(scene.get("source_url"))
    if source_url:
        label = clean_text(scene.get("source_label")) or "Source"
        source_label = "出典" if compact else "Source"
        parts.append(f'<p><b>{source_label}:</b> <a href="{html.escape(source_url)}">{html.escape(label)}</a></p>')
    reference_url = clean_text(scene.get("reference_url"))
    if reference_url and not compact:
        parts.append(f'<p><b>Reference:</b> <a href="{html.escape(reference_url)}">open reference</a></p>')
    if not compact:
        parts.append(f'<p><b>Google Maps:</b> <a href="{html.escape(google_maps_url(scene))}">open</a></p>')
    parts.append("</div>")
    return "\n".join(parts).replace("]]>", "]]&gt;")


def extended_data(scene: dict[str, Any], compact: bool = False) -> str:
    if compact:
        values = compact_kml_data(scene)
    else:
        values = csv_row(scene)
    parts = ["<ExtendedData>"]
    for key, value in values.items():
        if value:
            parts.append(f'<Data name="{xml(key)}"><value>{xml(value)}</value></Data>')
    parts.append("</ExtendedData>")
    return "\n".join(parts)


def compact_kml_data(scene: dict[str, Any]) -> dict[str, str]:
    match: ImageMatch = scene["_image_match"]
    values = {
        "作品": clean_text(scene.get("scene_title")),
        "出典": clean_text(scene.get("source_url")),
        "画像": image_links(match.images),
    }
    source_layer = clean_text(scene.get("source_layer"))
    if source_layer:
        values["元分類"] = source_layer
    confidence = clean_text(scene.get("confidence"))
    if confidence in {"probable", "unverified", "needs-review"}:
        values["確認"] = confidence
    return values


def compact_note(scene: dict[str, Any]) -> str:
    scene_title = clean_text(scene.get("scene_title"))
    if scene_title.startswith("Google Maps保存リスト"):
        memo = saved_list_memo(scene_title)
        if "2026年始VLOG" in memo:
            return "2026年始VLOG関連の補足地点。"
        if "四期生体力チェック" in memo:
            return "四期生企画関連の補足地点。"
        if "msg" in memo.lower():
            return "メッセージ由来の補足地点。"
        return "補足地点。"
    note = clean_text(scene.get("scene_note"))
    if len(note) > 90:
        return note[:87].rstrip() + "..."
    return note


def compact_title(scene: dict[str, Any]) -> str:
    title = clean_text(scene.get("scene_title"))
    if title.startswith("Google Maps保存リスト"):
        memo = saved_list_memo(title)
        if "msg" in memo.lower():
            return "メッセージ補足"
        return memo or clean_text(scene.get("name"))
    return title


def saved_list_memo(title: str) -> str:
    if "/" not in title:
        return ""
    return title.split("/", 1)[1].strip()


def write_match_report(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["id", "name", "source_article", "matched", "score", "reasons", "image_count", "block_text"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def match_report_row(scene: dict[str, Any], match: ImageMatch) -> dict[str, str]:
    return {
        "id": clean_text(scene.get("id")),
        "name": clean_text(scene.get("name")),
        "source_article": article_id_from_text(clean_text(scene.get("source_url"))) or "",
        "matched": "yes" if match.images else "no",
        "score": str(match.score),
        "reasons": "; ".join(match.reasons),
        "image_count": str(len(match.images)),
        "block_text": (match.block.text[:240] if match.block else ""),
    }


def write_readme(path: Path, layers: list[str], layer_filenames: dict[str, str]) -> None:
    lines = [
        "# 山川宇衣 My Maps KML 导入说明",
        "",
        "优先使用 `kml-with-images/` 里的 KML 文件。每个 KML 对应一个 My Maps 图层，地点说明里包含图片预览和出典。",
        "",
        "不要把 `yamakawa-ui-all_with_images.kml` 当正式版一次性导入；它适合预览，但后续维护图层不方便。",
        "",
        f"My Maps 单张地图最多 10 个图层，这版整理成 {len(layers)} 层。",
        "",
        "## 导入步骤",
        "",
        "1. 打开 Google My Maps，进入你的地图。",
        "2. 按下面顺序逐层点击 `インポート` / `Import`，选择对应的 `.kml` 文件。",
        "3. 如果第一层是空白默认图层，可以直接用它导入第一个 KML。",
        "4. 导入完成后检查弹窗图片。图片预览本身可点击打开原图。",
        "",
        "## Layer order",
        "",
    ]
    for idx, layer in enumerate(layers, start=1):
        lines.append(f"{idx}. `kml-with-images/{layer_filenames[layer]}.kml` - {layer}")
    lines.extend(
        [
            "",
            "## CSV 备份",
            "",
            "`mymaps-import-with-images/` 是 CSV 备份。CSV 适合普通地点导入，但图片通常只会作为链接字段，不如 KML 弹窗直观。",
            "",
            "CSV 导入时，位置列选 `Location`，标题列选 `Name`。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def ordered_layers(scenes: list[dict[str, Any]]) -> list[str]:
    present = []
    seen = set()
    for scene in scenes:
        layer = clean_text(scene.get("layer")) or "Unsorted"
        if layer not in seen:
            seen.add(layer)
            present.append(layer)
    ordered = [layer for layer in GROUP_LAYER_ORDER if layer in seen]
    ordered.extend(layer for layer in present if layer not in GROUP_LAYER_ORDER)
    return ordered


def grouped_layer(scene: dict[str, Any]) -> str:
    layer = clean_text(scene.get("layer"))
    source_url = clean_text(scene.get("source_url"))
    scene_title = clean_text(scene.get("scene_title"))
    tags = {clean_text(tag) for tag in scene.get("tags", [])}
    article_id = article_id_from_text(source_url) or ""

    if layer == "YouTube" or "YouTube" in tags:
        return "Youtube"
    if article_id == "59798375" or "ソロキャンプ" in layer or "ソロキャンプ" in scene_title:
        return "Youtube"
    if "2026年始vlog" in scene_title.lower() or any("2026年始vlog" in tag.lower() for tag in tags):
        return "Youtube"
    if source_url and layer == "山川宇衣 Vlog - 仙台・松島":
        return "四期生デビューVlog仙台松島"
    if layer == "四期生合宿 - 山中湖":
        return "四期生合宿_山中湖"
    if layer in {"個人PV - UITAN", "個人PV - その日、その場所で出会う。"}:
        return "個人PV"
    if layer == "光源 PV":
        return "光源MV"
    if layer == "四期生PV・グループMV" or "PV" in tags or "MV" in tags or "四期生体力チェック" in scene_title:
        return "四期生MVそこさく収録"
    return "MSG&雑誌&Blog"


def build_layer_filenames(layers: list[str]) -> dict[str, str]:
    preferred = {
        "四期生デビューVlog仙台松島": "01_四期生デビューVlog仙台松島",
        "Youtube": "02_Youtube",
        "四期生合宿_山中湖": "03_四期生合宿_山中湖",
        "個人PV": "04_個人PV",
        "光源MV": "05_光源MV",
        "四期生MVそこさく収録": "06_四期生MVそこさく収録",
        "MSG&雑誌&Blog": "07_MSG&雑誌&Blog",
    }
    filenames = {}
    for idx, layer in enumerate(layers, start=1):
        filenames[layer] = preferred.get(layer, f"{idx:02d}_{human_slug(layer)}")
    return filenames


def location_value(scene: dict[str, Any]) -> str:
    lat = clean_text(scene.get("lat"))
    lng = clean_text(scene.get("lng"))
    if lat and lng:
        return f"{lat},{lng}"
    return clean_text(scene.get("address")) or clean_text(scene.get("name"))


def google_maps_url(scene: dict[str, Any]) -> str:
    lat = clean_text(scene.get("lat"))
    lng = clean_text(scene.get("lng"))
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    query = clean_text(scene.get("address")) or clean_text(scene.get("name"))
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def image_links(images: list[ArticleImage]) -> str:
    return " | ".join(image.full for image in images)


def style_id(scene: dict[str, Any]) -> str:
    key = human_slug(clean_text(scene.get("category")) or "other").lower()
    return key if key in CATEGORY_COLORS else "other"


def human_slug(value: str) -> str:
    cleaned = re.sub(r"[\\/:\*\?\"<>\|&]+", "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "layer"


def article_id_from_html(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return article_id_from_text(text)


def article_id_from_text(value: str) -> str | None:
    match = re.search(r"/archives/(\d+)\.html", value)
    if match:
        return match.group(1)
    match = re.search(r"(\d{8})", value)
    return match.group(1) if match else None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def xml(value: Any) -> str:
    return html.escape(clean_text(value), quote=True)


if __name__ == "__main__":
    main()
