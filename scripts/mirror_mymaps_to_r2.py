#!/usr/bin/env python3
"""
Mirror Google My Maps images to Cloudflare R2 and rewrite GeoJSON to point to R2 URLs.

Usage:
  python3 mirror_mymaps_to_r2.py <geojson_file> [--prefix <r2_key_prefix>] [--dry-run]

Example:
  python3 mirror_mymaps_to_r2.py tokyo10sha.geojson --prefix seichi/tokyo10sha
  python3 mirror_mymaps_to_r2.py all  # process all seichi geojson files

Strategy:
  1. Read GeoJSON, collect all unique mymaps.usercontent.google.com URLs
  2. Download each to local cache dir (parallel, 8 threads)
  3. Upload to R2 bucket 'yamagawaui-map' with wrangler
  4. Rewrite GeoJSON images[] to R2 URLs
  5. Save mapping (source URL -> R2 URL) for reuse
"""
import json
import os
import sys
import hashlib
import subprocess
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time
import argparse

# --- Config ---
R2_BUCKET = 'yamagawaui-map'
R2_PUBLIC_BASE = 'https://pub-6d7574c4452b4452b41519ab8adf1541d7f9e.r2.dev'
# Fix: use the actual known-working base
R2_PUBLIC_BASE = 'https://pub-6d7574c4452b41519ab8adf1541d7f9e.r2.dev'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

PLATFORM_PUBLIC = Path('/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/sakamichi-platform/public/seichi')
CACHE_DIR = Path('/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps/assets/mymaps-cache')
MAPPING_FILE = Path('/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps/assets/mymaps-r2-mapping.json')


def load_existing_mapping():
    """Load existing URL mapping to skip already-mirrored images."""
    if MAPPING_FILE.exists():
        with open(MAPPING_FILE) as f:
            return json.load(f)
    return {}


def save_mapping(mapping):
    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def collect_mymaps_urls(geojson_path):
    """Extract all unique Google My Maps image URLs from a GeoJSON file."""
    with open(geojson_path, encoding='utf-8') as f:
        data = json.load(f)
    urls = set()
    for ft in data.get('features', []):
        props = ft.get('properties', {})
        for key in ('images', 'manual_images', 'article_images'):
            for u in props.get(key) or []:
                if 'mymaps.usercontent.google.com' in u:
                    urls.add(u)
    return sorted(urls), data


def url_to_filename(url):
    """Generate a stable filename from a My Maps URL."""
    # Extract the unique token part after /m/*/
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.split('/')
    # Find the long token (last significant segment)
    token = ''
    for part in reversed(path_parts):
        if len(part) > 20:
            token = part
            break
    if not token:
        token = hashlib.sha256(url.encode()).hexdigest()[:40]
    # Use first 40 chars of token + hash for uniqueness
    short = token[:40]
    full_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f'{short}_{full_hash}.png'


def download_image(url, local_path, retries=3):
    """Download a single image to local_path."""
    if local_path.exists() and local_path.stat().st_size > 100:
        return True, 'cached'
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) < 100:
                    return False, f'too small ({len(data)} bytes)'
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                return True, f'downloaded ({len(data)} bytes)'
        except Exception as e:
            if attempt == retries - 1:
                return False, f'{type(e).__name__}: {e}'
            time.sleep(1)
    return False, 'unknown'


def upload_to_r2(local_path, r2_key, content_type='image/png'):
    """Upload a file to R2 using wrangler."""
    cmd = [
        'npx', 'wrangler', 'r2', 'object', 'put',
        f"{R2_BUCKET}/{r2_key}",
        '--file', str(local_path),
        '--content-type', content_type,
        '--remote',
        '--cache-control', 'public,max-age=31536000,immutable'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                cwd='/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合')
        if result.returncode == 0:
            return True, 'uploaded'
        else:
            return False, f'wrangler exit {result.returncode}: {result.stderr[:200]}'
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'


def process_geojson(geojson_path, r2_prefix, mapping, dry_run=False):
    """Process a single GeoJSON file: download, upload, rewrite."""
    name = Path(geojson_path).stem
    print(f"\n{'='*60}")
    print(f"Processing: {geojson_path}")
    print(f"R2 prefix:  {r2_prefix}")
    print(f"{'='*60}")

    urls, data = collect_mymaps_urls(geojson_path)
    print(f"Found {len(urls)} unique My Maps image URLs")

    if not urls:
        print("  No My Maps images to mirror, skipping.")
        return

    # Phase 1: Download all images
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    to_process = []  # (url, local_path, r2_key, r2_url)

    for url in urls:
        if url in mapping:
            # Already mirrored
            to_process.append((url, None, None, mapping[url]))
            continue
        fname = url_to_filename(url)
        local_path = CACHE_DIR / fname
        r2_key = f'{r2_prefix}/{fname}'
        r2_url = f'{R2_PUBLIC_BASE}/{r2_key}'
        to_process.append((url, local_path, r2_key, r2_url))

    need_download = [(u, lp) for u, lp, rk, ru in to_process if lp is not None]
    print(f"\n--- Phase 1: Download {len(need_download)} images (8 parallel) ---")

    downloaded = 0
    failed_download = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_image, u, lp): u for u, lp in need_download}
        for i, fut in enumerate(as_completed(futures)):
            ok, msg = fut.result()
            url = futures[fut]
            if ok:
                downloaded += 1
            else:
                failed_download += 1
                print(f"  [FAIL] {url[:80]}... -> {msg}")
            if (i + 1) % 50 == 0 or (i + 1) == len(need_download):
                print(f"  Progress: {i+1}/{len(need_download)} (ok={downloaded}, fail={failed_download})")

    print(f"  Download complete: {downloaded} ok, {failed_download} failed")

    if dry_run:
        print("\n[DRY RUN] Skipping upload and GeoJSON rewrite.")
        return

    # Phase 2: Upload to R2
    need_upload = [(u, lp, rk, ru) for u, lp, rk, ru in to_process
                   if lp is not None and lp.exists()]
    print(f"\n--- Phase 2: Upload {len(need_upload)} images to R2 ---")

    uploaded = 0
    failed_upload = 0
    for i, (url, lp, rk, ru) in enumerate(need_upload):
        ok, msg = upload_to_r2(lp, rk)
        if ok:
            uploaded += 1
            mapping[url] = ru
            # Save mapping periodically
            if (uploaded % 20) == 0:
                save_mapping(mapping)
        else:
            failed_upload += 1
            print(f"  [FAIL] {rk} -> {msg}")
        if (i + 1) % 50 == 0 or (i + 1) == len(need_upload):
            print(f"  Progress: {i+1}/{len(need_upload)} (ok={uploaded}, fail={failed_upload})")

    save_mapping(mapping)
    print(f"  Upload complete: {uploaded} ok, {failed_upload} failed")

    # Phase 3: Rewrite GeoJSON
    print(f"\n--- Phase 3: Rewrite GeoJSON to use R2 URLs ---")
    replaced = 0
    for ft in data.get('features', []):
        props = ft.get('properties', {})
        for key in ('images', 'manual_images', 'article_images'):
            imgs = props.get(key)
            if not imgs:
                continue
            new_imgs = []
            for u in imgs:
                if u in mapping:
                    new_imgs.append(mapping[u])
                    replaced += 1
                else:
                    new_imgs.append(u)
            props[key] = new_imgs

    # Write back
    with open(geojson_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Replaced {replaced} image URLs with R2 URLs")
    print(f"  Saved: {geojson_path}")


# --- Map definitions ---
GEOJSON_MAPS = [
    ('tokyo10sha.geojson', 'seichi/tokyo10sha'),
    ('oversea.geojson', 'seichi/oversea'),
    ('sakurazaka-all.geojson', 'seichi/sakurazaka'),
    ('keyakizaka-all.geojson', 'seichi/keyakizaka'),
    ('fumi-sakurazaka.geojson', 'seichi/fumi-sakurazaka'),
]


def main():
    parser = argparse.ArgumentParser(description='Mirror Google My Maps images to R2')
    parser.add_argument('target', help='GeoJSON filename (e.g. tokyo10sha.geojson) or "all"')
    parser.add_argument('--prefix', help='R2 key prefix (auto-detected if omitted)')
    parser.add_argument('--dry-run', action='store_true', help='Download only, skip upload/rewrite')
    args = parser.parse_args()

    mapping = load_existing_mapping()
    print(f"Loaded {len(mapping)} existing URL mappings")

    if args.target == 'all':
        for fname, prefix in GEOJSON_MAPS:
            path = PLATFORM_PUBLIC / fname
            if path.exists():
                process_geojson(path, prefix, mapping, args.dry_run)
            else:
                print(f"  [SKIP] {path} not found")
    else:
        path = PLATFORM_PUBLIC / args.target
        if not path.exists():
            print(f"Error: {path} not found")
            sys.exit(1)
        prefix = args.prefix
        if not prefix:
            # Auto-detect from map definitions
            for fname, p in GEOJSON_MAPS:
                if fname == args.target:
                    prefix = p
                    break
        if not prefix:
            prefix = f'seichi/{Path(args.target).stem}'
        process_geojson(path, prefix, mapping, args.dry_run)

    print(f"\n✅ Done! Total mappings: {len(mapping)}")


if __name__ == '__main__':
    main()
