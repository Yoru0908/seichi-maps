#!/usr/bin/env python3
"""scenes.json → GeoJSON for MapLibre GL rendering."""
import json
import os
import re
import sys

JSON_PATH = os.path.join(os.path.dirname(__file__), 'yamakawa-ui-scenes.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'geojson')

# 6-layer grouping (must match build_kml_final.py logic)
LAYER_KEYS = [
    '01_四期生デビューVlog仙台松島',
    '02_Youtube',
    '03_四期生合宿_山中湖',
    '04_個人PV',
    '05_四期生MV_そこさく収録',
    '06_MSG_雑誌_Blog',
]

LAYER_DISPLAY = {
    '01_四期生デビューVlog仙台松島': '四期生デビューVlog - 仙台・松島',
    '02_Youtube': 'YouTube企画・ソロキャンプ・長野巡礼',
    '03_四期生合宿_山中湖': '四期生合宿 - 山中湖',
    '04_個人PV': '個人PV（UITAN・その日その場所で）',
    '05_四期生MV_そこさく収録': '四期生楽曲MV・そこさく収録',
    '06_MSG_雑誌_Blog': 'MSG・雑誌グラビア・公式Blog',
}

# Layer colors for map markers
LAYER_COLORS = {
    '01_四期生デビューVlog仙台松島': '#e11d48',  # rose
    '02_Youtube': '#7c3aed',  # violet
    '03_四期生合宿_山中湖': '#0891b2',  # cyan
    '04_個人PV': '#059669',  # emerald
    '05_四期生MV_そこさく収録': '#d97706',  # amber
    '06_MSG_雑誌_Blog': '#4f46e5',  # indigo
}


def classify_layer(scene):
    """Classify a scene into one of 6 layers (matches build_kml_final.py)."""
    name = scene.get('name', '')
    layer = scene.get('layer', '')

    if '仙台' in layer or '松島' in layer:
        if name in ['国宝 大崎八幡宮', '深沼海水浴場']:
            return '02_Youtube'
        elif name in ['仙台うみの杜水族館']:
            return '06_MSG_雑誌_Blog'
        else:
            return '01_四期生デビューVlog仙台松島'
    elif 'YouTube' in layer or 'ソロキャンプ' in layer:
        return '02_Youtube'
    elif '合宿' in layer or '山中湖' in layer:
        return '03_四期生合宿_山中湖'
    elif '個人PV' in layer or 'UITAN' in layer:
        return '04_個人PV'
    elif '光源' in layer or '四期生PV' in layer or 'MV' in layer or 'そこさく' in layer or 'We got your back' in name:
        return '05_四期生MV_そこさく収録'
    else:
        return '06_MSG_雑誌_Blog'

R2_BASE = 'https://pub-6d7574c4452b41519ab8adf1541d7f9e.r2.dev/yamakawa-ui'


PHOTO_MAPPING_PATH = os.path.join(os.path.dirname(__file__), 'photo_urls_mapping.json')
PHOTO_MAPPING = {}
if os.path.exists(PHOTO_MAPPING_PATH):
    with open(PHOTO_MAPPING_PATH, 'r', encoding='utf-8') as f:
        PHOTO_MAPPING = json.load(f)


def extract_image_urls(scene):
    """Extract image URLs from scene + photo_urls_mapping, sorting high-res first."""
    urls = []
    name = scene.get('name', '')

    # 1. Check scene's manual_images
    for img in scene.get('manual_images', []):
        u = img.get('full') or img.get('thumb')
        if u and u not in urls:
            if u.startswith('local:'):
                local_path = u[6:]
                u = f'{R2_BASE}/manual/{local_path}'
            urls.append(u)

    # 2. Check scene's images array
    for img in scene.get('images', []):
        if isinstance(img, str) and img not in urls:
            urls.append(img)
        elif isinstance(img, dict):
            u = img.get('full') or img.get('thumb') or img.get('src')
            if u and u not in urls:
                urls.append(u)

    # 3. Check photo_urls_mapping (covers fumi blog, R2, and We got your back)
    if name in PHOTO_MAPPING:
        for u in PHOTO_MAPPING[name]:
            if u and u not in urls:
                urls.append(u)

    # 4. Check article_images
    for img in scene.get('article_images', []):
        u = img.get('full') or img.get('src')
        if u and u not in urls:
            urls.append(u)

    # Sort so full-res .jpg comes before -s.jpg (thumbnails)
    full_res = [u for u in urls if not u.endswith('-s.jpg')]
    thumbs = [u for u in urls if u.endswith('-s.jpg')]
    
    return full_res + thumbs


def get_layer_display(scene):
    """Get the display layer name for a scene."""
    layer_key = classify_layer(scene)
    return LAYER_DISPLAY.get(layer_key, layer_key)


# === 大层级与小层级分类映射 ===

CATEGORY_COLORS = {
    'MV・楽曲': '#e11d48',      # 玫红
    'Vlog・企画': '#0891b2',    # 青蓝
    '個人PV': '#059669',        # 翠绿
    '雑誌・グラビア': '#7c3aed', # 紫罗兰
    'Blog・MSG': '#f59e0b',     # 琥珀橙
}

def get_hierarchy(scene):
    """提取大层级（Category）与小层级（Subcategory）。"""
    name = scene.get('name', '')
    layer = scene.get('layer', '')
    title = scene.get('scene_title', '')
    source = scene.get('source_label', '')

    # 1. MV・楽曲
    if '光源' in layer or '光源' in title:
        return 'MV・楽曲', '光源'
    if 'We got your back' in name or 'We got your back' in title or 'We got your back' in source:
        return 'MV・楽曲', 'We got your back'
    if 'Alter ego' in title or 'Alter ego' in source:
        return 'MV・楽曲', 'Alter ego'
    if '死んだふり' in title or '死んだふり' in source:
        return 'MV・楽曲', '死んだふり'
    if '四期生PV' in layer or 'MV' in layer or 'そこさく' in layer:
        return 'MV・楽曲', '四期生楽曲MV'

    # 2. 個人PV
    if 'UITAN' in layer or 'UITAN' in title:
        return '個人PV', 'UITAN'
    if 'その日' in layer or 'その日' in title:
        return '個人PV', 'その日、その場所で出会う。'
    if '個人PV' in layer:
        return '個人PV', 'その他個人PV'

    # 3. Vlog・企画
    if '仙台' in layer or '松島' in layer or '仙台' in title or '松島' in title:
        if name in ['国宝 大崎八幡宮', '深沼海水浴場']:
            return 'Vlog・企画', 'YouTube企画・ロケ'
        elif name == '仙台うみの杜水族館':
            return 'Blog・MSG', 'ブログ写真・グリーティング'
        return 'Vlog・企画', 'デビューVlog 仙台・松島'
    if '櫻旅' in title or '長野' in title or 'YouTube' in layer:
        return 'Vlog・企画', '櫻旅 長野編'
    if '合宿' in layer or '山中湖' in layer:
        return 'Vlog・企画', '四期生合宿 山中湖'
    if 'ソロキャンプ' in layer or 'ソロキャンプ' in title:
        return 'Vlog・企画', 'ソロキャンプ'
    if '2026始' in title or '初日の出' in title:
        return 'Vlog・企画', '2026年始Vlog'
    if 'Vlog' in layer:
        return 'Vlog・企画', 'その他Vlog'

    # 4. 雑誌・グラビア
    if '雑誌' in layer or '雑誌' in title:
        if '2026' in layer or '2026' in title:
            return '雑誌・グラビア', '2026年 掲載'
        return '雑誌・グラビア', '2025年 掲載'

    # 5. Blog・MSG
    return 'Blog・MSG', 'ブログ写真・グリーティング'


def scene_to_feature(scene):
    """Convert a scene to a GeoJSON Feature."""
    lat = scene.get('lat')
    lng = scene.get('lng')
    if lat is None or lng is None:
        return None

    category, subcategory = get_hierarchy(scene)
    cat_color = CATEGORY_COLORS.get(category, '#666666')
    image_urls = extract_image_urls(scene)

    props = {
        'id': scene.get('id', ''),
        'name': scene.get('name', ''),
        'category': category,
        'subcategory': subcategory,
        'categoryColor': cat_color,
        'address': scene.get('address', ''),
        'sceneTitle': scene.get('scene_title', ''),
        'sceneNote': scene.get('scene_note', ''),
        'sourceLabel': scene.get('source_label', ''),
        'sourceUrl': scene.get('source_url', ''),
        'referenceUrl': scene.get('reference_url', ''),
        'tags': scene.get('tags', []),
        'images': image_urls,
        'members': scene.get('tags', []) if any(m in scene.get('tags', []) for m in ['山川宇衣']) else ['山川宇衣'],
    }

    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [lng, lat]
        },
        'properties': props
    }

    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [lng, lat]  # GeoJSON uses [lng, lat]
        },
        'properties': props
    }


def main():
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    scenes = data.get('scenes', data) if isinstance(data, dict) else data

    features = []
    skipped = 0
    for s in scenes:
        feat = scene_to_feature(s)
        if feat:
            features.append(feat)
        else:
            skipped += 1

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, 'yamakawa-ui.geojson')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    # Also copy to platform public dir
    platform_public = os.path.join(
        os.path.dirname(__file__), '..', '..', 'sakamichi-platform', 'public', 'seichi'
    )
    os.makedirs(platform_public, exist_ok=True)
    platform_path = os.path.join(platform_public, 'yamakawa-ui.geojson')
    with open(platform_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    # Stats
    cat_counts = {}
    for feat in features:
        cat = feat['properties']['category']
        sub = feat['properties']['subcategory']
        key = f"{cat} > {sub}"
        cat_counts[key] = cat_counts.get(key, 0) + 1

    print(f'Generated GeoJSON: {len(features)} features ({skipped} skipped)')
    print(f'  Output: {output_path}')
    print(f'  Platform: {platform_path}')
    print(f'  Hierarchy counts:')
    for k in sorted(cat_counts.keys()):
        print(f'    {k}: {cat_counts[k]}')


if __name__ == '__main__':
    main()
