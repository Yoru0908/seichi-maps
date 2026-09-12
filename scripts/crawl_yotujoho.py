#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crawl_yotujoho.py — Scrape yotujoho.com (聖地巡礼したい) for Sakurazaka46 & Hinatazaka46
MV shooting locations.

Crawls:
  1. Sakurazaka46 category (all pages, follow pagination)
  2. Hinatazaka46 category (all pages, follow pagination)
  3. Hinatazaka46 summary page (hinatazaka46-rokechi) with big table of all MV locations

For each article extracts: title, url, date, group, location names, Google Maps links,
images, and parsed coordinates from embed URLs.

Output: scraped_yotujoho.json (UTF-8)
"""

import json
import re
import time
import sys
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://yotujoho.com"
SAKURAZAKA_CAT = "https://yotujoho.com/category/%e6%ab%bb%e5%9d%8246/"
HINATAZAKA_CAT = "https://yotujoho.com/category/%e6%97%a5%e5%90%91%e5%9d%8246/"
HINATAZAKA_SUMMARY = "https://yotujoho.com/hinatazaka46-rokechi/"

OUTPUT_PATH = "/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps/scraped_yotujoho.json"

DELAY = 0.3  # seconds between requests
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# Japanese prefecture prefixes used to split concatenated location text in tables
PREFECTURE_PATTERN = re.compile(
    r"(北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|"
    r"茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|"
    r"新潟県|富山県|石川県|福井県|山梨県|長野県|"
    r"岐阜県|静岡県|愛知県|三重県|"
    r"滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|"
    r"鳥取県|島根県|岡山県|広島県|山口県|"
    r"徳島県|香川県|愛媛県|高知県|"
    r"福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県|海外)"
)

# Coordinate extraction from embed pb parameter
# Streetview embed: !6m8!1m7!1s<pano_id>!2m2!1d<LAT>!2d<LNG>
# Place embed: !1m18!1m12!1m3!1d...!2d<LNG>!3d<LAT>
# Search embed: !1m5!1m4!1m3!1d...!2d<LNG>!3d<LAT>
COORD_LAT_RE = re.compile(r"!3d(-?\d+\.\d+)")
COORD_LNG_RE = re.compile(r"!2d(-?\d+\.\d+)")
# Street View style: !2m2!1d<LAT>!2d<LNG>
SV_LAT_RE = re.compile(r"!2m2!1d(-?\d+\.\d+)!2d(-?\d+\.\d+)")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
_session = requests.Session()
_session.headers.update(HEADERS)


def fetch(url: str) -> str:
    """Fetch a URL and return HTML text, with retry."""
    for attempt in range(3):
        try:
            resp = _session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:
            print(f"  [WARN] fetch attempt {attempt+1} failed for {url}: {exc}",
                  file=sys.stderr)
            if attempt < 2:
                time.sleep(1.0)
    print(f"  [ERROR] Giving up on {url}", file=sys.stderr)
    return ""


# ---------------------------------------------------------------------------
# Coordinate extraction
# ---------------------------------------------------------------------------
def extract_coords_from_pb(pb: str):
    """Extract (lat, lng) from a Google Maps embed pb parameter."""
    # Street View style: !2m2!1d<LAT>!2d<LNG>
    m = SV_LAT_RE.search(pb)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Place/search style: !3d<LAT> ... !2d<LNG>
    lat_m = COORD_LAT_RE.search(pb)
    lng_m = COORD_LNG_RE.search(pb)
    if lat_m and lng_m:
        return float(lat_m.group(1)), float(lng_m.group(1))
    return None, None


def parse_maps_url(url: str):
    """Parse a Google Maps URL and return dict with url, type, coords."""
    info = {"url": url, "type": None, "lat": None, "lng": None, "place_id": None}

    if "/maps/embed" in url:
        info["type"] = "embed"
        # Extract pb parameter
        pb_match = re.search(r"[?&]pb=([^&]+)", url)
        if pb_match:
            pb = unquote(pb_match.group(1))
            lat, lng = extract_coords_from_pb(pb)
            info["lat"] = lat
            info["lng"] = lng
    elif "/maps/place/" in url:
        info["type"] = "place"
        # Try to extract coords from place URL
        coord_match = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", url)
        if coord_match:
            info["lat"] = float(coord_match.group(1))
            info["lng"] = float(coord_match.group(2))
    elif "/maps/search/" in url or "query=" in url:
        info["type"] = "search"
        q_match = re.search(r"[?&]query=([^&]+)", url)
        if q_match:
            info["query"] = unquote(q_match.group(1))
            # query may contain lat,lng
            coord_match = re.match(r"^(-?\d+\.\d+),(-?\d+\.\d+)$", info["query"])
            if coord_match:
                info["lat"] = float(coord_match.group(1))
                info["lng"] = float(coord_match.group(2))
    elif "goo.gl/maps" in url or "maps.app.goo.gl" in url:
        info["type"] = "shortlink"
    else:
        info["type"] = "other"

    return info


# ---------------------------------------------------------------------------
# Category crawling
# ---------------------------------------------------------------------------
def crawl_category(category_url: str, group: str):
    """Crawl all pages of a category and return list of article metadata."""
    articles = []
    url = category_url
    page_num = 1

    while url:
        print(f"[{group}] Crawling page {page_num}: {url}")
        html = fetch(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main", class_="main-hb") or soup.find("main") or soup

        # Article cards are <a class="linkarea"> with h2.kiji-text inside
        cards = main.select("a.linkarea")
        if not cards:
            # Fallback: any link containing an h2.kiji-text
            cards = [a for a in main.find_all("a", href=True)
                     if a.find("h2", class_="kiji-text")]

        for card in cards:
            href = card.get("href", "")
            if not href or "/category/" in href:
                continue
            article_url = urljoin(BASE_URL, href)

            h2 = card.find("h2", class_="kiji-text")
            title = h2.get_text(strip=True) if h2 else ""

            time_el = card.find("time")
            date = ""
            if time_el:
                date = time_el.get("datetime", "") or time_el.get_text(strip=True)

            # Thumbnail image
            thumb = ""
            img = card.find("img")
            if img:
                thumb = img.get("data-src") or img.get("src", "")
                if "space.png" in thumb:
                    thumb = img.get("data-src", "")

            articles.append({
                "title": title,
                "url": article_url,
                "date": date,
                "group": group,
                "thumbnail": thumb,
                "locations": [],
                "images": [],
            })

        # Find next page link
        next_link = None
        next_a = soup.find("a", class_="next")
        if next_a:
            next_link = next_a.get("href", "")
        elif soup.find("a", string=re.compile(r"^次")):
            next_link = soup.find("a", string=re.compile(r"^次")).get("href", "")

        if next_link and next_link != url:
            url = urljoin(BASE_URL, next_link)
            page_num += 1
            time.sleep(DELAY)
        else:
            url = None

    return articles


# ---------------------------------------------------------------------------
# Article detail extraction
# ---------------------------------------------------------------------------
def extract_article_detail(article: dict):
    """Fetch an article page and extract locations, maps links, and images."""
    html = fetch(article["url"])
    if not html:
        return

    soup = BeautifulSoup(html, "html.parser")
    article_tag = soup.find("article")
    if not article_tag:
        return

    content = article_tag.find("section", class_="entry-letterbody")
    if not content:
        content = article_tag

    # Collect all h2 headings that represent location names
    h2s = content.find_all("h2")

    all_images = []
    all_maps = []

    for h2 in h2s:
        loc_name = h2.get_text(strip=True)

        maps_for_loc = []
        imgs_for_loc = []
        text_parts = []

        # Walk siblings until next h2
        el = h2.next_sibling
        while el:
            if hasattr(el, "name") and el.name == "h2":
                break
            if hasattr(el, "name") and el.name:
                # Google Maps iframes (lazy: data-src, noscript: src)
                seen_srcs = set()
                for iframe in el.find_all("iframe"):
                    src = iframe.get("data-src") or iframe.get("src", "")
                    if src and "google.com/maps" in src and src not in seen_srcs:
                        seen_srcs.add(src)
                        maps_for_loc.append(src)
                for ns in el.find_all("noscript"):
                    for iframe in ns.find_all("iframe"):
                        src = iframe.get("src", "")
                        if src and "google.com/maps" in src and src not in seen_srcs:
                            seen_srcs.add(src)
                            maps_for_loc.append(src)

                # Direct <a> links to Google Maps
                for a in el.find_all("a", href=True):
                    href = a["href"]
                    if ("google.com/maps" in href or "maps.app.goo.gl" in href
                            or "goo.gl/maps" in href):
                        if href not in seen_srcs:
                            seen_srcs.add(href)
                            maps_for_loc.append(href)

                # Images (exclude spacer/placeholder)
                for img in el.find_all("img"):
                    src = img.get("data-src") or img.get("src", "")
                    if src and "space.png" not in src and "wp-content" in src:
                        if src not in imgs_for_loc:
                            imgs_for_loc.append(src)

                # Collect text
                text = el.get_text(strip=True)
                if text and len(text) < 500:
                    text_parts.append(text)

            el = el.next_sibling

        # Parse maps URLs
        parsed_maps = [parse_maps_url(u) for u in maps_for_loc]

        location_entry = {
            "name": loc_name,
            "maps_urls": maps_for_loc,
            "maps_parsed": parsed_maps,
            "images": imgs_for_loc,
            "text": " ".join(text_parts)[:500] if text_parts else "",
        }

        article["locations"].append(location_entry)
        all_maps.extend(maps_for_loc)
        all_images.extend(imgs_for_loc)

    # If no h2 locations found, try to grab all maps iframes from content
    if not article["locations"]:
        seen = set()
        maps = []
        for iframe in content.find_all("iframe"):
            src = iframe.get("data-src") or iframe.get("src", "")
            if src and "google.com/maps" in src and src not in seen:
                seen.add(src)
                maps.append(src)
        for ns in content.find_all("noscript"):
            for iframe in ns.find_all("iframe"):
                src = iframe.get("src", "")
                if src and "google.com/maps" in src and src not in seen:
                    seen.add(src)
                    maps.append(src)
        if maps:
            article["locations"].append({
                "name": "(全体)",
                "maps_urls": maps,
                "maps_parsed": [parse_maps_url(u) for u in maps],
                "images": [],
                "text": "",
            })
            all_maps.extend(maps)

    # Collect all images from article (including thumbnail area)
    for img in article_tag.find_all("img"):
        src = img.get("data-src") or img.get("src", "")
        if src and "space.png" not in src and "wp-content/uploads" in src:
            if src not in all_images:
                all_images.append(src)

    article["images"] = all_images
    article["maps_count"] = len(all_maps)


# ---------------------------------------------------------------------------
# Hinatazaka46 summary page table parsing
# ---------------------------------------------------------------------------
def split_location_text(text: str):
    """Split concatenated location text by prefecture prefixes.

    e.g. "長野県公立諏訪東京理科大学佐久総合運動公園 陸上競技場"
    -> [{"prefecture": "長野県", "name": "公立諏訪東京理科大学佐久総合運動公園 陸上競技場"}]
    """
    # Find all prefecture positions
    positions = [(m.start(), m.end(), m.group()) for m in PREFECTURE_PATTERN.finditer(text)]
    if not positions:
        return [{"prefecture": "", "name": text.strip()}]

    locations = []
    for i, (start, end, pref) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        name = text[end:next_start].strip()
        # Remove trailing whitespace
        name = re.sub(r"\s+", " ", name).strip()
        if name:
            locations.append({"prefecture": pref, "name": name})
        else:
            locations.append({"prefecture": pref, "name": pref})
    return locations


def crawl_hinatazaka_summary():
    """Parse the Hinatazaka46 summary page with its big tables."""
    print(f"[Hinatazaka46まとめ] Crawling: {HINATAZAKA_SUMMARY}")
    html = fetch(HINATAZAKA_SUMMARY)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    results = []
    current_section = ""

    for table in tables:
        # Find the preceding heading for this table
        prev_heading = table.find_previous(["h2", "h3", "h4"])
        if prev_heading:
            current_section = prev_heading.get_text(strip=True)

        trs = table.find_all("tr")
        if not trs:
            continue

        # Skip header rows (first row with th or "MV" in text)
        data_rows = []
        for tr in trs:
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            # Check if header row
            first_text = cells[0].get_text(strip=True)
            if tr.find("th") or "MV" in first_text or "リンク" in first_text:
                continue
            data_rows.append(cells)

        for cells in data_rows:
            if len(cells) < 2:
                continue

            # Cell 0: MV name + YouTube link
            mv_cell = cells[0]
            mv_name = mv_cell.get_text(strip=True)
            yt_links = [a["href"] for a in mv_cell.find_all("a", href=True)
                        if "youtu" in a["href"]]

            # Cell 1: Locations text + Google Maps links
            loc_cell = cells[1]
            loc_text = loc_cell.get_text(separator="", strip=True)
            map_links = []
            for a in loc_cell.find_all("a", href=True):
                href = a["href"]
                if ("goo.gl/maps" in href or "maps.app.goo.gl" in href
                        or "google.com/maps" in href or "maps.google" in href):
                    map_links.append(href)

            # Split the location text by prefecture
            locations = split_location_text(loc_text)

            # Pair locations with map links as best we can
            # (links are in order of locations, but not always 1:1)
            for i, loc in enumerate(locations):
                if i < len(map_links):
                    loc["maps_url"] = map_links[i]
                    loc["maps_parsed"] = parse_maps_url(map_links[i])
                else:
                    loc["maps_url"] = None
                    loc["maps_parsed"] = None

            results.append({
                "section": current_section,
                "mv_name": mv_name,
                "youtube_url": yt_links[0] if yt_links else None,
                "location_text": loc_text,
                "locations": locations,
                "maps_links": map_links,
            })

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("yotujoho.com scraper — Sakurazaka46 & Hinatazaka46 MV locations")
    print("=" * 70)

    # 1. Crawl Sakurazaka46 category
    print("\n>>> Phase 1: Crawl Sakurazaka46 category pages")
    sakura_articles = crawl_category(SAKURAZAKA_CAT, "櫻坂46")
    print(f"    Found {len(sakura_articles)} Sakurazaka46 articles")

    # 2. Crawl Hinatazaka46 category
    print("\n>>> Phase 2: Crawl Hinatazaka46 category pages")
    hinata_articles = crawl_category(HINATAZAKA_CAT, "日向坂46")
    print(f"    Found {len(hinata_articles)} Hinatazaka46 articles")

    # 3. Extract article details
    print("\n>>> Phase 3: Extract article details (locations, maps, images)")
    all_articles = sakura_articles + hinata_articles
    total = len(all_articles)
    for i, art in enumerate(all_articles, 1):
        print(f"  [{i}/{total}] {art['title'][:50]}")
        extract_article_detail(art)
        loc_count = len(art.get("locations", []))
        map_count = art.get("maps_count", 0)
        print(f"    -> {loc_count} locations, {map_count} maps, "
              f"{len(art.get('images', []))} images")
        time.sleep(DELAY)

    # 4. Parse Hinatazaka46 summary page
    print("\n>>> Phase 4: Parse Hinatazaka46 summary page (rokechi table)")
    hinata_summary = crawl_hinatazaka_summary()
    print(f"    Found {len(hinata_summary)} MV entries in summary tables")

    # 5. Assemble output
    output = {
        "source": "yotujoho.com",
        "site_name": "聖地巡礼したい",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "sakurazaka46": {
            "category_url": SAKURAZAKA_CAT,
            "article_count": len(sakura_articles),
            "articles": sakura_articles,
        },
        "hinatazaka46": {
            "category_url": HINATAZAKA_CAT,
            "article_count": len(hinata_articles),
            "articles": hinata_articles,
            "summary_url": HINATAZAKA_SUMMARY,
            "summary_entries": hinata_summary,
        },
        "totals": {
            "sakurazaka46_articles": len(sakura_articles),
            "hinatazaka46_articles": len(hinata_articles),
            "hinatazaka46_summary_entries": len(hinata_summary),
            "total_articles": total,
        },
    }

    # 6. Write JSON
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n>>> Output written to: {OUTPUT_PATH}")
    print(f"    Sakurazaka46 articles: {len(sakura_articles)}")
    print(f"    Hinatazaka46 articles: {len(hinata_articles)}")
    print(f"    Hinatazaka46 summary entries: {len(hinata_summary)}")

    # Print summary stats
    sakura_locs = sum(len(a.get("locations", [])) for a in sakura_articles)
    sakura_maps = sum(a.get("maps_count", 0) for a in sakura_articles)
    hinata_locs = sum(len(a.get("locations", [])) for a in hinata_articles)
    hinata_maps = sum(a.get("maps_count", 0) for a in hinata_articles)
    hinata_summary_maps = sum(len(e.get("maps_links", [])) for e in hinata_summary)

    print(f"\n=== Summary ===")
    print(f"  Sakurazaka46: {sakura_locs} locations, {sakura_maps} maps links")
    print(f"  Hinatazaka46: {hinata_locs} locations, {hinata_maps} maps links")
    print(f"  Hinatazaka46 summary: {hinata_summary_maps} maps links")


if __name__ == "__main__":
    main()
