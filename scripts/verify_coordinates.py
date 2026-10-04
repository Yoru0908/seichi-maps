#!/usr/bin/env python3
"""scene 坐标 ↔ fumi Diary 原文坐标 的核对（防止「整理进 scenes.json 时被改坏」）。

背景：2026-08-20 的一次整理把 21 个 fumi 的点改偏了 35〜1052 m（六郷水门 1 km），之后一直没人发现——
fumi 原文的「座標:」是对的，错的是 scenes.json 里手抄的那份，而发布链路里没有任何一步对照原文。

做法：
  - `yamakawa-ui/fumi-coords.json`（提交进 git）= scenes 引用到的 fumi 文章里写明的坐标快照。
  - 每个 fumi 来源的 scene，坐标必须落在原文对应地点 TOL 米以内，否则判为 DRIFT。
  - build_geojson.py 在生成前离线调用 guard()：有 DRIFT 就不生成，错坐标发布不出去。
  - 确实要和原文不同（例如 fumi 自己写错了）：在 scene 里写 `"coord_override": "原因"`，报告里会一直列出来。

用法（在 seichi-maps 目录）：
  python3 scripts/verify_coordinates.py              # 核对；快照里没有的文章会联网抓取并补进快照
  python3 scripts/verify_coordinates.py --refresh    # 重新抓取所有引用到的文章，报告 fumi 原文是否改过
  python3 scripts/verify_coordinates.py --fix        # 把 DRIFT 的点恢复成原文坐标（先备份 scenes.json）
  python3 scripts/verify_coordinates.py --gsi        # 另对「原文没写坐标」的点用国土地理院地址检索做粗核对（只警告）
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "yamakawa-ui" / "yamakawa-ui-scenes.json"
SNAPSHOT = ROOT / "yamakawa-ui" / "fumi-coords.json"
TOL_M = 15.0
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
ARTICLE = re.compile(r"fumichen2/archives/(\d+)")
COORD = re.compile(r"座標\s*[:：]\s*(-?\d+\.\d+)\s*[,，\s]\s*(-?\d+\.\d+)")
JAPAN = (20.0, 46.5, 122.0, 154.0)  # lat min/max, lng min/max


def article_id(url: str | None) -> str | None:
    m = ARTICLE.search(url or "")
    return m.group(1) if m else None


def norm(text: str | None) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"〒?\d{3}-\d{4}", "", t)
    return re.sub(r"[\s・/／\-－–—~〜()（）「」『』,、。]+", "", t).lower()


def meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot((b[0] - a[0]) * 111_200, (b[1] - a[1]) * 111_320 * math.cos(math.radians(a[0])))


# ---------- 原文解析 ----------

URL_LINE = re.compile(r"^https?://", re.I)
ADDRESS_LINE = re.compile(r"^(?:〒\s*\d{3}-\d{4}\s*)?[^\s]{2,4}[都道府県]")


def looks_like_name(line: str) -> bool:
    """地名は短い。感想の一文（句点で終わる／長い）は地名ではない。"""
    return bool(line) and len(line) <= 40 and not line.endswith("。") and not URL_LINE.match(line)


def parse_article(html: str) -> list[dict[str, Any]]:
    """文章里每个「座標: lat, lng」→ {name, address, lat, lng}。

    版式：地点名 / (URL) / 〒地址 / 座標。地址只在**紧挨着**座標行时才属于该坐标（中间隔着感想文字的地址属于别的、没写坐标的地点）；
    前面是感想文字时，该坐标没有地点名（name 为空）。
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("div", class_="article-body-inner") or soup.find("div", class_="article-body")
    if body is None:
        return []
    for br in body.find_all("br"):
        br.replace_with("\n")
    lines = [ln.strip().replace("\xa0", " ") for ln in body.get_text("\n").split("\n") if ln.strip()]
    spots = []
    for i, line in enumerate(lines):
        m = COORD.search(line)
        if not m:
            continue
        address = name = ""
        prev = lines[i - 1] if i else ""
        if ADDRESS_LINE.match(prev) and not COORD.search(prev):
            address = prev
            for j in range(i - 2, max(-1, i - 4), -1):  # 地址之前（可隔一行 URL）才是地点名
                if URL_LINE.match(lines[j]):
                    continue
                name = lines[j] if looks_like_name(lines[j]) and not COORD.search(lines[j]) else ""
                break
        elif looks_like_name(prev) and not COORD.search(prev):
            name = prev
        spots.append({"name": name, "address": address, "lat": float(m.group(1)), "lng": float(m.group(2))})
    return spots


def fetch_article(url: str, retries: int = 3) -> str | None:
    url = url.replace("https://", "http://")
    for n in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            if n == retries - 1:
                print(f"  [fetch failed] {url}: {e}", file=sys.stderr)
            time.sleep(1.5)
    return None


# ---------- 快照 ----------

def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"articles": {}, "pins": {}}


def save_snapshot(snap: dict[str, Any], path: Path = SNAPSHOT) -> None:
    snap["articles"] = dict(sorted(snap["articles"].items()))
    snap["pins"] = dict(sorted(snap.get("pins", {}).items()))
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_snapshot(scenes: list[dict], snap: dict[str, Any], refresh: bool = False, online: bool = True) -> dict[str, list[str]]:
    """补齐（或 --refresh 重抓）scenes 引用到的 fumi 文章。返回 {'added': [...], 'changed': [...], 'failed': [...]}。"""
    out: dict[str, list[str]] = {"added": [], "changed": [], "failed": []}
    urls = {}
    for s in scenes:
        aid = article_id(s.get("source_url"))
        if aid:
            urls.setdefault(aid, s["source_url"])
    for aid, url in sorted(urls.items()):
        have = aid in snap["articles"]
        if have and not refresh:
            continue
        if not online:
            if not have:
                out["failed"].append(aid)
            continue
        html = fetch_article(url)
        time.sleep(0.5)
        if html is None:
            out["failed"].append(aid)
            continue
        spots = parse_article(html)
        if have and snap["articles"][aid]["spots"] != spots:
            out["changed"].append(aid)
        elif not have:
            out["added"].append(aid)
        snap["articles"][aid] = {"url": url, "fetchedAt": datetime.date.today().isoformat(), "spots": spots}
    return out


# ---------- 核对 ----------

def match_spots(scene: dict, spots: list[dict]) -> list[tuple[int, dict]]:
    """scene 在文章里**明确**对应的地点（地址或地名完全相同，得分 ≥ 3）。并列都返回。

    地名只是包含关系（「至誠荘」⊂「至誠荘への小径」）不算明确对应——那常常是同一处的不同地点。
    """
    addr, name = norm(scene.get("address")), norm(scene.get("name"))
    scored = []
    for sp in spots:
        sa, sn = norm(sp["address"]), norm(sp["name"])
        score = 0
        if addr and sa and addr == sa and re.search(r"\d", addr):  # 只到町村名的地址不能区分地点
            score += 4
        if name and sn and name == sn:
            score += 3
        if score:
            scored.append((score, sp))
    best = max((sc for sc, _ in scored), default=0)
    return [(sc, sp) for sc, sp in scored if sc == best]


def check_scene(scene: dict, snap: dict[str, Any], tol: float = TOL_M) -> dict[str, Any]:
    """status:
    ok         坐标等于文章里写明的某个坐标（±tol）
    drift      明确对应某个原文地点，但坐标和文章里所有坐标都对不上
    override   同 drift，但 scene 写了 coord_override（原因）
    unverified 文章有坐标，但没有明确对应的地点（原文只写了地址等）→ 无法用原文核对
    no_article 文章不在快照里 / not_fumi 非 fumi 来源 / no_coord 无坐标
    """
    res: dict[str, Any] = {"id": scene.get("id"), "name": scene.get("name"), "status": "not_fumi"}
    if not isinstance(scene.get("lat"), (int, float)) or not isinstance(scene.get("lng"), (int, float)):
        res["status"] = "no_coord"
        return res
    aid = article_id(scene.get("source_url"))
    if not aid:
        return res
    art = snap["articles"].get(aid)
    if art is None:
        res["status"] = "no_article"
        return res
    here = (scene["lat"], scene["lng"])
    if not art["spots"]:
        res["status"] = "unverified"
        return res
    near = min(art["spots"], key=lambda sp: meters(here, (sp["lat"], sp["lng"])))
    res["nearest"] = (near["lat"], near["lng"])
    res["nearest_dist"] = meters(here, res["nearest"])
    if res["nearest_dist"] <= tol:
        res["status"] = "ok"
        res["pin"] = res["nearest"]
        return res
    cands = match_spots(scene, art["spots"])
    pin = snap.get("pins", {}).get(scene.get("id"))
    if not cands and pin:  # 地名对不上，但这个点曾被核对过（pins）：不能离开核对过的位置
        res.update(dist=meters(here, tuple(pin)), fumi=tuple(pin), exact=True)
        res["status"] = "override" if str(scene.get("coord_override") or "").strip() else "drift"
        return res
    if not cands:
        res["status"] = "unverified"
        return res
    best = min((sp for _, sp in cands), key=lambda sp: meters(here, (sp["lat"], sp["lng"])))
    res.update(dist=meters(here, (best["lat"], best["lng"])), fumi=(best["lat"], best["lng"]),
               exact=len(cands) == 1 and norm(cands[0][1]["name"]) == norm(scene.get("name")))
    res["status"] = "override" if str(scene.get("coord_override") or "").strip() else "drift"
    return res


def sanity(scenes: list[dict]) -> list[str]:
    """与来源无关的底线：坐标在日本范围内、没把 lat/lng 写反、id 不重复。"""
    problems, seen = [], set()
    for s in scenes:
        lat, lng, sid = s.get("lat"), s.get("lng"), s.get("id")
        if sid in seen:
            problems.append(f"{sid}: id 重复")
        seen.add(sid)
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            if not (JAPAN[0] <= lat <= JAPAN[1] and JAPAN[2] <= lng <= JAPAN[3]):
                problems.append(f"{sid}: 坐标 ({lat}, {lng}) 不在日本范围内（lat/lng 写反了？）")
    return problems


def update_pins(snap: dict[str, Any], results: list[dict[str, Any]]) -> int:
    """与原文一致的点 → 钉住其坐标。之后即使 scene 改名/换地名写法，也不能离开这个位置。"""
    pins = snap.setdefault("pins", {})
    new = {r["id"]: list(r["pin"]) for r in results if r["status"] == "ok" and pins.get(r["id"]) != list(r["pin"])}
    pins.update(new)
    return len(new)


def check_scenes(scenes: list[dict], snap: dict[str, Any], tol: float = TOL_M) -> list[dict[str, Any]]:
    return [check_scene(s, snap, tol) for s in scenes]


def guard(scenes: list[dict] | None = None, snap: dict[str, Any] | None = None) -> None:
    """build_geojson.py 用：离线核对，有 DRIFT / 底线问题就退出，错坐标进不了 GeoJSON。"""
    if scenes is None:
        data = json.loads(SCENES.read_text(encoding="utf-8"))
        scenes = data.get("scenes", data) if isinstance(data, dict) else data
    snap = snap or load_snapshot()
    results = check_scenes(scenes, snap)
    bad = [r for r in results if r["status"] == "drift"]
    problems = sanity(scenes)
    unchecked = [r for r in results if r["status"] == "no_article"]
    if unchecked:
        print(f"⚠ {len(unchecked)} 个点引用的 fumi 文章不在快照里，坐标未核对（运行 scripts/verify_coordinates.py 补齐）", file=sys.stderr)
    if not bad and not problems:
        return
    print("✘ 坐标核对未通过，已停止生成：", file=sys.stderr)
    for r in bad:
        print(f"  {r['id']}  与 fumi 原文相差 {r['dist']:.0f} m（原文 {r['fumi'][0]}, {r['fumi'][1]}）", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print("  → 运行 `python3 scripts/verify_coordinates.py --fix` 恢复原文坐标；确需不同请在 scene 写 coord_override（原因）", file=sys.stderr)
    sys.exit(1)


# ---------- GSI 粗核对（原文没有坐标的点） ----------

def gsi_geocode(address: str) -> tuple[float, float, str] | None:
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(address)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            hits = json.load(r)
    except Exception:  # noqa: BLE001
        return None
    if not hits:
        return None
    lng, lat = hits[0]["geometry"]["coordinates"]
    return lat, lng, hits[0]["properties"].get("title", "")


def gsi_threshold(address: str) -> float | None:
    """地址精度 → 容许偏差。到番地（以数字结尾）：600 m；到丁目：2500 m；只到町村：不核对。"""
    a = unicodedata.normalize("NFKC", address).strip()
    if a.endswith("丁目"):
        return 2500.0
    return 600.0 if re.search(r"\d$", a) else None


# ---------- 备份 / 修复 ----------

def apply_fix(path: Path, fixes: dict[str, tuple[float, float]]) -> Path:
    """只替换 lat/lng 两行，保持文件其余部分逐字不变。"""
    text = path.read_text(encoding="utf-8")
    backup = path.with_name(f"{path.name}.bak.{datetime.datetime.now():%Y%m%d_%H%M%S}_coord_fix")
    shutil.copy2(path, backup)
    for sid, (lat, lng) in fixes.items():
        i = text.index(f'"id": "{sid}"')
        j = text.index("}", i)
        block = text[i:j]
        new, n = re.subn(r'("lat": )-?\d+(?:\.\d+)?(,\s*"lng": )-?\d+(?:\.\d+)?', rf"\g<1>{lat}\g<2>{lng}", block, count=1)
        if n != 1:
            raise SystemExit(f"{sid}: 找不到 lat/lng 行，未修改")
        text = text[:i] + new + text[j:]
    path.write_text(text, encoding="utf-8")
    return backup


# ---------- CLI ----------

def restore_targets(drifts: list[dict], scenes: list[dict], snap: dict[str, Any], backup: Path, tol: float) -> dict[str, tuple[float, float]]:
    """DRIFT 的点 → 备份里的旧坐标，前提是旧坐标本身就是该文章写明的某个坐标（原文背书，不是随便一个旧值）。"""
    data = json.loads(backup.read_text(encoding="utf-8"))
    old = {s["id"]: s for s in (data.get("scenes", data) if isinstance(data, dict) else data)}
    by_id = {s["id"]: s for s in scenes}
    out = {}
    for r in drifts:
        prev, cur = old.get(r["id"]), by_id[r["id"]]
        if r["id"] in snap.get("pins", {}):
            out[r["id"]] = tuple(snap["pins"][r["id"]])
            continue
        if not prev or not isinstance(prev.get("lat"), (int, float)):
            continue
        spots = snap["articles"][article_id(cur["source_url"])]["spots"]
        hit = min(spots, key=lambda sp: meters((prev["lat"], prev["lng"]), (sp["lat"], sp["lng"])))
        if meters((prev["lat"], prev["lng"]), (hit["lat"], hit["lng"])) <= tol:
            out[r["id"]] = (hit["lat"], hit["lng"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="重新抓取所有引用到的 fumi 文章，报告原文变化")
    ap.add_argument("--fix", action="store_true", help="DRIFT 且地名完全相同的唯一地点：恢复成原文坐标（先备份）")
    ap.add_argument("--restore-from", type=Path, metavar="BACKUP", help="DRIFT 的点：恢复成该备份里的旧坐标（旧坐标必须是原文写明的坐标）")
    ap.add_argument("--gsi", action="store_true", help="对无法用原文核对的点，用国土地理院地址检索粗核对（只警告）")
    ap.add_argument("--offline", action="store_true", help="不联网，只用快照")
    ap.add_argument("--tol", type=float, default=TOL_M, help=f"容许偏差（米，默认 {TOL_M:.0f}）")
    args = ap.parse_args()

    data = json.loads(SCENES.read_text(encoding="utf-8"))
    scenes = data.get("scenes", data) if isinstance(data, dict) else data
    snap = load_snapshot()
    sync = sync_snapshot(scenes, snap, refresh=args.refresh, online=not args.offline)
    if sync["added"] or sync["changed"] or args.refresh:
        save_snapshot(snap)
    print(f"fumi 文章快照：{len(snap['articles'])} 篇（新增 {len(sync['added'])}，原文变化 {len(sync['changed'])}，抓取失败 {len(sync['failed'])}）")
    for aid in sync["changed"]:
        print(f"  ⚠ 原文有变化 {aid}  {snap['articles'][aid]['url']}  → 请确认 fumi 是否更正了坐标")

    results = check_scenes(scenes, snap, args.tol)
    if update_pins(snap, results):
        save_snapshot(snap)
    by: dict[str, list[dict]] = {}
    for r in results:
        by.setdefault(r["status"], []).append(r)
    label = {"ok": "与原文一致", "drift": "与原文不符 (DRIFT)", "override": "有 coord_override", "unverified": "原文无法核对",
             "no_article": "文章不在快照里", "not_fumi": "非 fumi 来源", "no_coord": "无坐标"}
    print(f"scenes {len(scenes)}：" + "，".join(f"{label[k]} {len(v)}" for k, v in by.items()))
    for r in sorted(by.get("drift", []), key=lambda r: -r["dist"]):
        print(f"  DRIFT {r['dist']:>5.0f} m  {r['id']:36} 原文 {r['fumi'][0]}, {r['fumi'][1]}")
    for r in by.get("override", []):
        print(f"  override {r['dist']:>5.0f} m  {r['id']}")
    for p in sanity(scenes):
        print(f"  ✘ {p}")

    if args.gsi:
        print("\n地址粗核对（国土地理院，只核对到番地/丁目的地址）：")
        by_id = {s["id"]: s for s in scenes}
        for r in results:
            if r["status"] not in ("unverified", "not_fumi", "no_article"):
                continue
            s = by_id[r["id"]]
            limit = gsi_threshold(s.get("address") or "")
            g = gsi_geocode(s["address"]) if limit else None
            time.sleep(0.3)
            if g and (d := meters((s["lat"], s["lng"]), g[:2])) > limit:
                print(f"  ⚠ {s['id']:36} 离地址 {d:.0f} m（>{limit:.0f}）  {s['address']}")

    drifts = by.get("drift", [])
    if args.restore_from:  # 地名对不上的点也要看：备份里的旧值若正是文章写明的坐标，就是被改坏的
        drifts = drifts + [r for r in by.get("unverified", []) if "nearest" in r and r["nearest_dist"] > args.tol]
    fixes: dict[str, tuple[float, float]] = {}
    if args.fix:
        fixes = {r["id"]: r["fumi"] for r in drifts if r["exact"]}
    if args.restore_from:
        fixes |= restore_targets(drifts, scenes, snap, args.restore_from, args.tol)
    if args.fix or args.restore_from:
        if fixes:
            print(f"\n已恢复 {len(fixes)} 个点的坐标；备份：{apply_fix(SCENES, fixes).name}")
        left = [r["id"] for r in by.get("drift", []) if r["id"] not in fixes]
        if left:
            print(f"需人工处理（没有唯一明确的原文坐标可恢复）：{', '.join(left)}")
        return 1 if left else 0
    return 1 if drifts else 0


if __name__ == "__main__":
    sys.exit(main())
