#!/usr/bin/env python3
"""Keep only images referenced by generated KML plus manual images."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune an R2 image map to actually used KML images.")
    parser.add_argument("--image-map", required=True, type=Path)
    parser.add_argument("--kml-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    all_rows = json.loads(args.image_map.read_text(encoding="utf-8"))["images"]
    used_sources = used_livedoor_urls(args.kml_dir)
    kept = [
        row
        for row in all_rows
        if row["source"].startswith("local:") or row["source"] in used_sources
    ]
    missing = sorted(used_sources - {row["source"] for row in kept})
    if missing:
        raise SystemExit("Missing mirrored URLs:\n" + "\n".join(missing[:20]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_map = args.output_dir / "r2-image-map-used.json"
    out_cmds = args.output_dir / "wrangler-upload-used-commands.txt"
    out_map.write_text(json.dumps({"images": kept}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_cmds.write_text("\n".join(upload_command(row) for row in kept) + "\n", encoding="utf-8")

    print(json.dumps({"kept": len(kept), "fumi": len([r for r in kept if not r["source"].startswith("local:")]), "manual": len([r for r in kept if r["source"].startswith("local:")]), "mapping": str(out_map)}, ensure_ascii=False, indent=2))


def used_livedoor_urls(kml_dir: Path) -> set[str]:
    urls: set[str] = set()
    for path in sorted(kml_dir.glob("*.kml")):
        text = path.read_text(encoding="utf-8")
        for url in re.findall(r"https://livedoor\.blogimg\.jp/fumichen2/[^\"<> ]+", text):
            urls.add(url.replace("&amp;", "&"))
    return urls


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
