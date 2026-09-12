#!/usr/bin/env python3
"""Mirror fumi livedoor images for the Yamakawa Ui seichi map."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


def main() -> None:
    parser = argparse.ArgumentParser(description="Download fumi images and write an R2 URL mapping.")
    parser.add_argument("--articles-dir", required=True, type=Path)
    parser.add_argument("--extra-article", action="append", default=[], type=Path)
    parser.add_argument("--manual-images-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--public-base-url", required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fumi_dir = args.output_dir / "fumi"
    manual_dir = args.output_dir / "manual"
    fumi_dir.mkdir(exist_ok=True)
    manual_dir.mkdir(exist_ok=True)

    mappings: list[dict[str, str]] = []
    source_urls = extract_fumi_image_urls(args.articles_dir, args.extra_article)
    for index, url in enumerate(source_urls, start=1):
        rel = f"yamakawa-ui/fumi/{remote_filename(url, index)}"
        local = fumi_dir / Path(rel).name
        download(url, local)
        mappings.append(mapping_row(url, local, rel, args.public_base_url))

    for local in sorted(args.manual_images_dir.glob("*/*")):
        if not local.is_file() or local.name.startswith("."):
            continue
        rel = f"yamakawa-ui/manual/{local.parent.name}/{local.name}"
        mirror = manual_dir / local.parent.name / local.name
        mirror.parent.mkdir(parents=True, exist_ok=True)
        if not mirror.exists() or mirror.stat().st_size != local.stat().st_size:
            mirror.write_bytes(local.read_bytes())
        mappings.append(mapping_row(f"local:{local.relative_to(args.manual_images_dir)}", mirror, rel, args.public_base_url))

    mapping_path = args.output_dir / "r2-image-map.json"
    mapping_path.write_text(json.dumps({"images": mappings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_manifest = args.output_dir / "wrangler-upload-commands.txt"
    upload_manifest.write_text("\n".join(upload_command(row) for row in mappings) + "\n", encoding="utf-8")

    print(json.dumps({"images": len(mappings), "mapping": str(mapping_path)}, ensure_ascii=False, indent=2))


def extract_fumi_image_urls(articles_dir: Path, extra_articles: list[Path]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for path in sorted(articles_dir.glob("*.html")) + extra_articles:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        for img in soup.find_all("img"):
            src = clean_url(img.get("src", ""))
            if "livedoor.blogimg.jp/fumichen2" not in src:
                continue
            for candidate in [full_image_url(img, src), src]:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    urls.append(candidate)
    return urls


def full_image_url(img: object, fallback: str) -> str:
    parent = getattr(img, "parent", None)
    if parent and getattr(parent, "name", None) == "a":
        href = clean_url(parent.get("href", ""))
        if href.startswith("http"):
            return href
    return fallback


def clean_url(value: str) -> str:
    return str(value or "").strip()


def remote_filename(url: str, index: int) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower() or ".jpg"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    base = Path(parsed.path).stem
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-") or f"image-{index:03d}"
    return f"{index:03d}_{base}_{digest}{suffix}"


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as response:
        path.write_bytes(response.read())
    time.sleep(0.08)


def mapping_row(source: str, local: Path, key: str, public_base_url: str) -> dict[str, str]:
    return {
        "source": source,
        "local": str(local),
        "key": key,
        "url": public_base_url.rstrip("/") + "/" + key,
        "content_type": mimetypes.guess_type(local.name)[0] or "application/octet-stream",
    }


def upload_command(row: dict[str, str]) -> str:
    return (
        "npx wrangler r2 object put "
        f"yamagawaui-map/{shell_quote(row['key'])} "
        f"--file {shell_quote(row['local'])} "
        f"--content-type {shell_quote(row['content_type'])} "
        "--remote "
        "--cache-control public,max-age=31536000,immutable"
    )


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
