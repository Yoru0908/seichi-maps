# 圣巡地图平台架构设计

## 目标

自建圣巡地图平台，替代 Google My Maps。支持多维度筛选（成员/内容类型/企划），一个地点可以属于多个分类。先做山川宇衣，后续可扩展其他成员。

## URL 结构

```
/seichi                          ← 入口页：成员列表 + 介绍
/seichi/yamakawa-ui              ← 山川宇衣地图
/seichi/[member-slug]            ← 未来扩展其他成员
```

## 数据结构

### scenes.json（权威数据源，已有）

每个 scene 已有的字段：
- `name` — 地点名
- `layer` — 原始层分类
- `lat` / `lng` — 坐标
- `address` — 地址
- `scene_title` — 场景标题
- `scene_note` — 场景描述
- `source_url` / `source_label` — 出处
- `manual_images` / `article_images` — 图片
- `tags` — 标签数组（多维度分类的关键）

### 新增的分类维度（从现有字段推导，不改 JSON）

1. **按成员**：从 tags 中提取成员名（山川宇衣、小田倉麗奈等）
2. **按内容类型**：从 layer / scene_title 推导
   - MV（光源 / Alter ego / 死んだふり / We got your back）
   - Vlog（仙台松島 / 山中湖 / ソロキャンプ / 2026始Vlog）
   - YouTube企画（櫻旅長野編）
   - 雑誌（2025 / 2026）
   - Blog / MSG
   - 個人PV（UITAN / その日その場所で）
3. **按企划**：从 source_label / scene_title 推导
   - 櫻旅 長野編
   - 2026年始Vlog
   - 光源 PV
   - We got your back
   - Alter ego
   - 死んだふり
   - 四期生合宿 山中湖
   - etc.

### GeoJSON 生成（build_geojson.py）

每个 Feature 的 properties：
```json
{
  "name": "善光寺",
  "member": ["山川宇衣"],
  "contentType": ["YouTube企画"],
  "project": ["櫻旅 長野編"],
  "layer": "02_Youtube",
  "layerKey": "02_Youtube",
  "address": "長野県長野市元善町401",
  "sceneTitle": "櫻旅 長野編 / 善光寺",
  "sceneNote": "...",
  "sourceLabel": "櫻坂チャンネル / 櫻旅 長野編",
  "sourceUrl": "https://www.youtube.com/watch?v=...",
  "images": ["https://..."],
  "tags": ["山川宇衣", "櫻旅", "長野", "善光寺"],
  "id": "sakuratabi-nagano-zenkoji"
}
```

## 前端架构

### 技术栈
- Astro 页面 + React 组件（island）
- MapLibre GL JS（开源地图引擎，免费无 API key）
- Tailwind CSS（已有）
- 数据：静态 GeoJSON 文件（`/public/seichi/yamakawa-ui.geojson`）

### 页面布局

```
┌─────────────────────────────────────────────┐
│  Navbar（复用现有）                           │
├──────────┬──────────────────────────────────┤
│ 侧边栏    │                                  │
│          │         MapLibre GL 地图          │
│ 搜索框    │                                  │
│          │    ●    ●        ●               │
│ 筛选区    │       ●     ●                    │
│ - 成员    │    ●          ●                  │
│ - 类型    │                                  │
│ - 企划    │                                  │
│          │                                  │
│ 地点列表  │                                  │
│ (可滚动)  │                                  │
│          │                                  │
├──────────┴──────────────────────────────────┤
│  数据来源声明 / 转载标注                       │
└─────────────────────────────────────────────┘
```

### 交互逻辑

1. **地图渲染**：MapLibre GL 加载 GeoJSON，按 layerKey 分组着色
2. **筛选**：多维度 checkbox 筛选，实时更新地图显示的点
3. **搜索**：输入框实时搜索地点名/地址/tag
4. **点击标记**：
   - 弹出弹窗显示：地点名、图片、地址、场景描述、出处链接
   - 两个按钮：
     - 「Google Maps で開く」→ `https://www.google.com/maps/search/?api=1&query=lat,lng`
     - 「ナビ開始」→ `https://www.google.com/maps/dir/?api=1&destination=lat,lng`
5. **侧边栏地点列表**：点击列表项飞到地图对应位置
6. **移动端**：侧边栏变为底部抽屉，地图全屏

### 数据来源声明

页面底部显示：
```
データ出典：
- 櫻坂チャンネル YouTube
- fumi Diary 2号店 (http://blog.livedoor.jp/fumichen2/) — ロケ地参考
- 各公式ブログ / 雑誌
※ 転載禁止の画像は使用せず、出典リンクのみ掲載
```

## 构建流程

```
scenes.json (权威数据)
    ↓ build_geojson.py
yamakawa-ui.geojson (含多维度分类)
    ↓ 复制到
sakamichi-platform/public/seichi/yamakawa-ui.geojson
    ↓ Astro build
部署到 Cloudflare Pages
```

改了 scenes.json → 跑 `python3 build_geojson.py` → 重新部署 → 地图自动更新

## 文件结构

```
sakamichi-platform/src/
├── pages/seichi/
│   ├── index.astro              ← 入口页
│   └── yamakawa-ui.astro        ← 山川宇衣地图页
├── components/seichi/
│   ├── SeichiMap.tsx            ← MapLibre GL 地图组件
│   ├── Sidebar.tsx              ← 侧边栏（搜索+筛选+列表）
│   └── Popup.tsx                ← 点击弹窗
└── ...

sakamichi-platform/public/seichi/
└── yamakawa-ui.geojson          ← 生成的 GeoJSON
```
