#!/usr/bin/env python3
"""
Full pagination scraper for fumi Diary 2号店 (Sakurazaka46 & Hinatazaka46/Keyakizaka46).
Crawl all pages for each tag, parse all scene spots, coordinates, descriptions, and high-res images.
"""
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import json
import re
import os
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

TAGS = [
    # 櫻坂46 全体 & 企画
    '櫻坂46', '櫻坂チャンネル',
    # 櫻坂46 一二期生
    '森田ひかる', '田村保乃', '藤吉夏鈴', '守屋麗奈', '山﨑天', '小池美波', '大園玲', '武元唯衣', '松田里奈', '井上梨名', '増本綺良', '大沼晶保', '幸阪茉里乃',
    # 櫻坂46 三期生
    '的野美青', '山下瞳月', '谷口愛季', '村井優', '中嶋優月', '小島凪紗', '村山美羽', '遠藤理子', '小田倉麗奈', '石森璃花', '向井純葉',
    # 櫻坂46 四期生
    '山川宇衣', '佐藤愛桜', '浅井恋乃未', '稲熊ひな', '勝又春', '中川智尋', '松本和子', '目黒陽色', '山田桃実',
    # 日向坂46 / けやき坂46
    'けやき坂46', '金村美玖', '小坂菜緒', '加藤史帆', '齊藤京子', '佐々木美玲', '佐々木久美', '丹生明里', '河田陽菜', '松田好花', '東村芽依', '富田鈴花', '上村ひなの', '高本彩花', '濱岸ひより',
]

def fetch_html(url, retries=3):
    for r in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if r == retries - 1:
                print(f"    [Error] {url}: {e}")
                return None
            time.sleep(1)
    return None

def crawl_all_tag_links():
    all_article_links = {} # href -> {'title': title, 'tags': [tag]}
    
    print("=== Step 1: Crawling all tag pages with full pagination ===")
    for tag in TAGS:
        enc = urllib.parse.quote(tag)
        page = 1
        tag_count = 0
        
        while True:
            if page == 1:
                url = f"http://blog.livedoor.jp/fumichen2/tag/{enc}"
            else:
                url = f"http://blog.livedoor.jp/fumichen2/tag/{enc}?p={page}"
                
            html = fetch_html(url)
            if not html:
                break
                
            soup = BeautifulSoup(html, 'html.parser')
            h2s = soup.find_all('h2', class_='article-title')
            if not h2s:
                h2s = [h for h in soup.find_all(['h2', 'h1']) if h.find('a') and '/archives/' in (h.find('a').get('href') or '')]
                
            found = 0
            for h in h2s:
                a = h.find('a')
                if a and a.get('href') and '/archives/' in a.get('href') and a.get('href').endswith('.html'):
                    href = a.get('href')
                    title = a.text.strip()
                    if href not in all_article_links:
                        all_article_links[href] = {'title': title, 'tags': [tag]}
                    else:
                        if tag not in all_article_links[href]['tags']:
                            all_article_links[href]['tags'].append(tag)
                    found += 1
                    tag_count += 1
                    
            if found == 0:
                break
                
            # Check for next page link in pager
            has_next = False
            pager = soup.find('div', class_='pager')
            if pager:
                next_li = pager.find('li', class_='next')
                if next_li and next_li.find('a'):
                    has_next = True
            elif '次の5件' in html or '次のページ' in html:
                has_next = True
                
            if not has_next:
                break
                
            page += 1
            time.sleep(0.15)
            
        print(f"  Tag [{tag}]: crawled {page} pages -> {tag_count} articles")
        
    print(f"\nTotal unique articles to parse: {len(all_article_links)}")
    return all_article_links

def build_source_metadata(href, title, tags):
    if 'けやき坂46' in tags:
        group = 'けやき坂46'
    elif '日向坂46' in tags:
        group = '日向坂46'
    elif '櫻坂46' in tags or '櫻坂チャンネル' in tags:
        group = '櫻坂46'
    elif '欅坂46' in tags:
        group = '欅坂46'
    else:
        group = ''
    return {
        'provider': 'fumi Diary 2号店',
        'url': href,
        'layer': '',
        'tags': list(tags),
        'name': title,
        'group': group,
    }


def build_classification(tags):
    if 'けやき坂46' in tags:
        group = 'けやき坂46'
    elif '日向坂46' in tags:
        group = '日向坂46'
    elif '櫻坂46' in tags or '櫻坂チャンネル' in tags:
        group = '櫻坂46'
    elif '欅坂46' in tags:
        group = '欅坂46'
    else:
        group = ''
    return {
        'category': group,
        'subcategory': '',
        'method': 'source-tags',
        'status': 'source' if group else 'unreviewed',
    }


def build_common_fields(href, title, tags):
    return {
        'source': build_source_metadata(href, title, tags),
        'classification': build_classification(tags),
        'classificationCandidates': {
            'members': [],
            'projects': [],
            'contentTypes': [],
        },
        'members': [],
    }


def parse_article_content(href, meta):
    html = fetch_html(href)
    if not html:
        return []
        
    soup = BeautifulSoup(html, 'html.parser')
    title_el = soup.find('h2', class_='article-title')
    title = title_el.text.strip() if title_el else meta.get('title', '')
    
    body = soup.find('div', class_='article-body-inner') or soup.find('div', class_='article-body')
    if not body:
        return []
        
    date_el = soup.find('span', class_='article-date') or soup.find('div', class_='article-date')
    date_str = date_el.text.strip() if date_el else ''
    
    # Extract tags from article
    tags = list(meta.get('tags', []))
    for a in soup.find_all('a', href=lambda h: h and '/tag/' in h):
        t_name = a.text.strip()
        if t_name and t_name not in tags:
            tags.append(t_name)
            
    # Extract images (convert -s.jpg to high-res .jpg where available)
    raw_imgs = [img['src'] for img in body.find_all('img') if 'livedoor.blogimg.jp' in img.get('src', '')]
    high_res_imgs = []
    for u in raw_imgs:
        clean_u = re.sub(r'-s\.jpg$', '.jpg', u)
        if clean_u not in high_res_imgs:
            high_res_imgs.append(clean_u)
            
    # Parse text by paragraphs/blocks
    text = body.get_text()
    
    # Extract coordinates
    # Patterns: 座標: 35.657190, 139.693916 or 35.657190, 139.693916
    coord_matches = re.findall(r'座標:\s*([0-9\.]+)[,\s]+([0-9\.]+)', text)
    
    # Extract addresses: 〒xxx-xxxx ...
    addresses = re.findall(r'(〒[0-9]{3}-[0-9]{4}[^\n\r]+)', text)
    
    spots = []
    
    if coord_matches:
        for idx, (lat_s, lng_s) in enumerate(coord_matches):
            try:
                lat = float(lat_s)
                lng = float(lng_s)
            except ValueError:
                continue
                
            spot_name = title
            if len(coord_matches) > 1:
                spot_name = f"{title} #{idx+1}"
                
            addr = addresses[idx] if idx < len(addresses) else (addresses[0] if addresses else '')
            
            spots.append({
                **build_common_fields(href, title, tags),
                'name': spot_name,
                'article_title': title,
                'article_url': href,
                'date': date_str,
                'lat': lat,
                'lng': lng,
                'address': addr,
                'tags': tags,
                'images': high_res_imgs,
                'note': text[:500].strip(),
            })
    elif addresses:
        # Address found without explicit coords
        spots.append({
            **build_common_fields(href, title, tags),
            'name': title,
            'article_title': title,
            'article_url': href,
            'date': date_str,
            'lat': None,
            'lng': None,
            'address': addresses[0],
            'tags': tags,
            'images': high_res_imgs,
            'note': text[:500].strip(),
        })
        
    return spots

def main():
    article_links = crawl_all_tag_links()
    
    print("\n=== Step 2: Parsing each article ===")
    all_spots = []
    for idx, (href, meta) in enumerate(article_links.items()):
        spots = parse_article_content(href, meta)
        all_spots.extend(spots)
        if (idx + 1) % 25 == 0 or idx == len(article_links) - 1:
            print(f"  Parsed [{idx+1}/{len(article_links)}] articles -> {len(all_spots)} spots so far...")
        time.sleep(0.15)
        
    out_file = '/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps/scraped_fumi_all_sakura_hinata.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_spots, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Finished! Saved {len(all_spots)} spots to {out_file}")

if __name__ == '__main__':
    main()
