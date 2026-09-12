# Seichi Map Workflow

这个 workflow 用来维护山川宇衣巡礼地图的底图数据和 Google My Maps 导入文件。目标不是做普通地点合集，而是做可以按作品/来源分层、每个点都有场景说明和出处的巡礼地图。

> 新成员、朋友或 Agent 要新建其他成员地图时，先读根目录的 [`README.md`](README.md)：其中包含数据边界、图片授权/R2 规则、JSON 模板和两轮 Agent 协作提示词。本文件保留山川宇衣项目的实际路径与命令。

## 目录约定

- 项目根目录：`/Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps`
- 山川宇衣地图数据：`yamakawa-ui/yamakawa-ui-scenes.json`
- 最终 My Maps 导入目录：`yamakawa-ui/my-maps-kml-r2`
- 最终压缩包：`yamakawa-ui/yamakawa-ui-my-maps-kml-r2.zip`
- 本地手动图片：`yamakawa-ui/assets/manual-images`
- R2 镜像映射：`yamakawa-ui/assets/r2-mirror/r2-image-map.json`
- R2 bucket：`yamagawaui-map`
- R2 public base URL：`https://pub-6d7574c4452b41519ab8adf1541d7f9e.r2.dev`

不要把新文件写到旧的 `sakamichi-tools/seichi-maps`；统一放在 `sakamichi-tools项目统合/seichi-maps`。

## 数据原则

每个地点必须是一个“场景点”，而不是单纯的店名或地址。至少需要：

- `name`：地图上显示的地点名。
- `layer`：原始分类，后续会被生成器合并成 My Maps 实际图层。
- `category`：图标/颜色用，常用 `Restaurant`、`Shop`、`Shrine`、`Park`、`Station`、`Scene`、`Other`。
- `address` 或 `lat`/`lng`：优先用明确地址；经纬度只在确认无误时写入。
- `scene_title`：短标题，例如 `260408msg電話 / 甘味処 彦いち`。
- `scene_ref`：来源定位，例如 `260408msg電話`、`YouTube FasWElvoy9c / 10:12`。
- `scene_note`：给普通用户看的简短说明，不写过细考据。
- `source_url` / `source_label`：出处链接和显示名。
- `confidence`：`confirmed`、`probable`、`unverified`、`needs-review`。
- `access_note`：店铺营业时间、神社礼仪、设施开放情况等简短提醒。
- `tags`：检索和后续分组用。

未确认日期时可以先写 `scene_ref: "MSG / 日付未確認"`，确认后再改成 `260408msg電話` 这种格式。

## 图层规则

My Maps 实际层数按 10 层以内控制。当前生成器严格对齐线上地图的 7 层：

1. `四期生デビューVlog仙台松島`
2. `Youtube`
3. `四期生合宿_山中湖`
4. `個人PV`
5. `光源MV`
6. `四期生MVそこさく収録`
7. `MSG&雑誌&Blog`

杂志、blog、MSG 补充点统一归入 `MSG&雑誌&Blog`。个人 PV 合并到 `個人PV`。四期生 PV 和 group MV 合并到 `四期生MVそこさく収録`。所有 YouTube 视频（包括 2026 年始 Vlog、单人露营和长野篇）统一归入 `Youtube`，不要再拆出单独图层。

## 图片规则

My Maps 不会把 KML 描述中的外部 `<img src="...">` 自动转成地图图片附件。R2 负责保证图片 URL 公开可访问，并可在 KML/CSV 中作为图片链接保存；但要让图片显示在 My Maps 点位弹窗里，必须在点位编辑界面使用「画像または動画を追加」粘贴 R2 URL，让 My Maps 自己托管图片。

手动图片存放格式：

```text
yamakawa-ui/assets/manual-images/<place-slug>/01_original.<ext>
yamakawa-ui/assets/manual-images/<place-slug>/01_thumb.<ext>
```

JSON 中使用 `local:` 引用：

```json
"manual_images": [
  {
    "thumb": "local:<place-slug>/01_thumb.jpg",
    "full": "local:<place-slug>/01_original.jpg",
    "label": "260408msg電話 / 甘味処 彦いち"
  }
]
```

生成前要刷新 R2 映射；生成后的 KML 里不应出现 `local:` 或 livedoor 图片直链。

## 新增地点流程

1. 确认地点是否公开、是否适合做巡礼点。不要加入私人住址、学校生活地点、实时位置或无法公开验证的敏感地点。
2. 在 `yamakawa-ui/yamakawa-ui-scenes.json` 追加一条 scene。
3. 如果有图片，放进 `assets/manual-images/<place-slug>/`，并生成缩略图。
4. 刷新 R2 镜像映射。
5. 上传新增图片到 R2。
6. 重新生成 KML/CSV。
7. 检查 KML 是否可解析，且没有 `local:`、livedoor 直链、过长原图列表。
8. 更新 zip。
9. 在 My Maps 里只导入受影响的图层 KML。

无图片的 MSG/电话提及点也可以先加入；这种点会没有弹窗图，但仍有地址、短说明和来源。

## 常用命令

从项目根目录执行：

```bash
cd /Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps
```

刷新图片映射：

```bash
python3 scripts/mirror_fumi_images.py \
  --articles-dir yamakawa-ui/tag-sources/articles \
  --extra-article yamakawa-ui/source-59716400.html \
  --manual-images-dir yamakawa-ui/assets/manual-images \
  --output-dir yamakawa-ui/assets/r2-mirror \
  --public-base-url https://pub-6d7574c4452b41519ab8adf1541d7f9e.r2.dev
```

上传新增手动图片到 R2：

```bash
npx wrangler r2 object put yamagawaui-map/yamakawa-ui/manual/<place-slug>/01_original.jpg \
  --file yamakawa-ui/assets/r2-mirror/manual/<place-slug>/01_original.jpg \
  --remote

npx wrangler r2 object put yamagawaui-map/yamakawa-ui/manual/<place-slug>/01_thumb.jpg \
  --file yamakawa-ui/assets/r2-mirror/manual/<place-slug>/01_thumb.jpg \
  --remote
```

重新生成 R2 KML/CSV：

```bash
python3 scripts/build_mymaps_with_images.py \
  --scenes yamakawa-ui/yamakawa-ui-scenes.json \
  --articles-dir yamakawa-ui/tag-sources/articles \
  --extra-article yamakawa-ui/source-59716400.html \
  --output yamakawa-ui/my-maps-kml-r2 \
  --title '山川宇衣 巡礼マップ' \
  --group-layers \
  --compact \
  --r2-map yamakawa-ui/assets/r2-mirror/r2-image-map.json
```

验证输出：

```bash
python3 -c "from pathlib import Path; from xml.etree import ElementTree as ET; base=Path('yamakawa-ui/my-maps-kml-r2'); [ET.parse(p) for p in sorted((base/'kml-with-images').glob('*.kml'))+[base/'yamakawa-ui-all_with_images.kml']]; print('parsed ok')"
grep -R -n "local:\|livedoor.blogimg\|Image 1\|原图" yamakawa-ui/my-maps-kml-r2/kml-with-images yamakawa-ui/my-maps-kml-r2/yamakawa-ui-all_with_images.kml
```

`grep` 没有输出才是正常。

更新 zip：

```bash
cd yamakawa-ui
zip -r yamakawa-ui-my-maps-kml-r2.zip my-maps-kml-r2
```

## My Maps 导入

正式导入优先使用：

```text
yamakawa-ui/my-maps-kml-r2/kml-with-images/
```

不要把 `yamakawa-ui-all_with_images.kml` 当正式版一次性导入。它适合预览，但后续维护图层不方便。

新增点后通常只需要重新导入受影响图层。例如 MSG/电话补充点导入：

```text
kml-with-images/07_雑誌_Blog.kml
```

YouTube 点导入：

```text
kml-with-images/08_Youtube.kml
```

导入后检查：

- 地点是否落在正确位置。
- 弹窗是否显示图片预览。
- 说明是否简洁。
- 出典链接是否可打开。
- 图层名称是否和预期一致。

## 弹窗说明风格

保持短，不把考据过程塞进普通用户弹窗。

推荐：

```text
260408msg電話 / 甘味処 彦いち
MSG電話で言及された店。
住所: 宮城県仙台市青葉区一番町4丁目5-41
出典: Google Maps / user-provided
```

避免：

- 多个“原图: Image 1 / Image 2”链接列表。
- 很长的推理过程。
- 内部文件路径。
- 不必要的 confidence/access 细节，除非是 `needs-review`。

## 质量检查

交付前至少确认：

- `yamakawa-ui-scenes.json` 中 scene 数量符合预期。
- 新增点 id 唯一。
- 目标图层 KML 中能搜到新增点。
- KML XML 可解析。
- My Maps 可能只为整层选择一种定位列：纯坐标层只输出 `<Point>`；纯地址层输出 `<address>`；地址/坐标混合层中，精确坐标行同时输出“纬度, 经度”形式的 `<address>` 与 `<Point>`，原日文地址继续保留在说明中。这样可避免 Point 行被当成空地址而导入失败。
- KML 中没有 `local:` 图片引用。
- KML 中没有 livedoor 直链，除非是非图片的公开出处链接且确实需要保留。
- zip 已更新。
- My Maps 图层数量不超过 10。

## 当前注意事项

- R2 上已有 fumi/blog 相关图片镜像，后续继续保持 KML 使用 R2 URL。
- 只有 `仙台うみの杜水族館` 曾经没有图片；无图点可以保留。
- 如果 My Maps KML 导入失败，先尝试单层 KML；仍失败时用同目录 CSV 作为备份，但 CSV 的图片展示不如 KML。
- 新增 MSG 点如果还没有截图，可以先无图加入，等截图补齐后再加 `manual_images` 并上传 R2。
