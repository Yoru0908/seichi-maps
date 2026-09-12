# 巡礼地图制作指南（给人和 Agent）

这个目录用于制作「作品 / 企划 / 写真 / Vlog 中出现的公开地点」的 Google My Maps 巡礼地图。现有成品是 `yamakawa-ui/`（山川宇衣）；制作森田光版时，按同样结构新建 `morita-hikaru/`，不要混入山川宇衣目录。

地图的最小单位是**有证据的场景点**，不是单纯的店铺或地点收藏。每个点都要能回答：哪一个作品或内容出现了它、在哪里可核查、地图用户到现场应看什么、这个识别有多确定。

详细的山川宇衣维护命令见 [SEICHI_MAP_WORKFLOW.md](SEICHI_MAP_WORKFLOW.md)。本 README 是跨成员制作新地图、特别是让 Agent 协作时的入口。

## 成品与数据流

```text
公开作品 / 官方帖文 / 已公开的地点考据
        ↓  （人工或 Agent 提取、核查）
scenes.json：一个场景一行，含出处和置信度
        ↓
本地图片 + R2 图片映射（只放可公开使用的素材）
        ↓
build_mymaps_with_images.py
        ↓
按作品分层的 KML + CSV + zip
        ↓
Google My Maps：逐层导入并人工检查
```

- `scenes.json` 是唯一的地点数据正本；不要直接修改已生成的 KML/CSV。
- 图片存本地资产目录，KML 只引用 R2 的公开 HTTPS URL；Google My Maps 不能稳定携带本地图片。
- KML 是正式导入格式，CSV 是无图或 KML 导入失败时的备份。

## 先定边界：公开性、准确性与图片

只收录可公开验证、适合巡礼的地点，例如官方公开的 MV / Vlog / 博客 / 杂志拍摄地、公开活动场地和公开视频中明确出现的场景。

不要收录或推断私人住址、学校、工作场所、非公开行程、实时位置，或仅凭「看起来像」得出的敏感地点。地点还不能确认时可以保留为 `needs-review`，但不应把猜测写成事实。

图片不是地图的必要条件。优先级如下：

1. 有公开来源和地点证据，即使没有图片也可先入图。
2. 需要照片辅助辨认时，只放一到三张必要的缩略图 / 现场参考图；不要做作品截图或杂志页的再发布图库。
3. 只上传你有权公开上传的图片，或已明确允许再利用的图片。若权利不明，保留 `source_url` 作为出处，不把图片复制到 R2。
4. 不热链容易失效的第三方图床；经确认可用的图片上传到本地图专属 R2 bucket，再把公开 URL 写入 KML。

## 新建森田光版

建议先创建以下结构（名称可改，但全程保持一致）：

```text
morita-hikaru/
├── morita-hikaru-scenes.json       # 唯一地点数据正本
├── sources/                        # 链接清单、公开文章缓存、调查笔记
├── assets/
│   ├── manual-images/              # 已确认可公开上传的手动图片
│   └── r2-mirror/                  # 生成的 R2 映射和待上传副本
└── my-maps-kml-r2/                 # 生成物；不要手改
    └── kml-with-images/            # My Maps 正式逐层导入文件
```

给新项目确定一个独立的 R2 bucket、对象前缀和 public base URL，例如：

```text
bucket: <morita-hikaru-map-bucket>
prefix: morita-hikaru/
public base: https://<your-public-domain>/morita-hikaru/
```

不要把森田光图片上传进 `yamagawaui-map`，除非维护者明确决定这个 bucket 要作为所有成员地图的共享资产库，并且对象前缀、权限和成本都已规划好。

## 场景数据格式

一个物理地点在两个不同作品中出现时，应写成两条 scene：它们的场景说明、出处和置信度各自独立。`id` 必须唯一；经纬度仅在确认无误时填写，无法确认就保留为空并给出可搜索的 `address`。

```json
{
  "scenes": [
    {
      "id": "morita-example-mv-01",
      "name": "地点的正式名称",
      "layer": "作品名 / 年份",
      "category": "Scene",
      "address": "可由 Google Maps 搜到的公开地址",
      "lat": 35.0,
      "lng": 139.0,
      "scene_title": "作品名 / 具体镜头或照片",
      "scene_ref": "YouTube 视频 ID / 01:23，或发布日、页码",
      "scene_note": "一句到两句：它在内容中如何出现、现场可辨认的元素；不写长篇推理。",
      "source_url": "https://公开出处.example/",
      "source_label": "官方 MV / 官方博客 / 公开考据来源",
      "confidence": "confirmed",
      "access_note": "开放时间、拍摄礼仪、从公共区域观看等必要提醒。",
      "tags": ["森田ひかる", "MV", "地区名"],
      "manual_images": []
    }
  ]
}
```

`confidence` 只能使用以下值：

- `confirmed`：官方信息或多个可靠公开来源可直接确认。
- `probable`：特征高度吻合，但没有直接确认。
- `unverified`：有线索但尚未完成核查；尽量不作为正式公开图层的重点。
- `needs-review`：信息不足、地点不够明确或需要人工复核。

图层按「作品 / 企划 / 时期」分，而不是按餐厅、车站等地点类别分。Google My Maps 控制在约 10 层以内；作品太多时拆成两张地图。

## 图片处理

手动补充的图片采用固定路径，便于脚本与 R2 一一对应：

```text
assets/manual-images/<place-slug>/01_original.jpg
assets/manual-images/<place-slug>/01_thumb.jpg
```

其中 `place-slug` 使用稳定的英文小写名称，例如 `shibuya-crossing`；缩略图用于地图弹窗，原图只在确有必要时链接。处理要求：

- 去掉不必要的 EXIF/GPS 等元数据，图片大小保持适合网页加载。
- 不用带私人信息、聊天记录或未授权人物的照片。
- 每张图在 JSON 中注明它对应的场景，不用「Image 1」之类无意义名称。
- 上传 R2 后，重新生成映射；最终 KML 不得含 `local:`、本机路径或失效的第三方图片直链。

示例：

```json
"manual_images": [
  {
    "thumb": "local:shibuya-crossing/01_thumb.jpg",
    "full": "local:shibuya-crossing/01_original.jpg",
    "label": "作品名 / 路口远景"
  }
]
```

## 让 Agent 制作地图：推荐分两轮

第一轮只做资料表和证据核查，不生成地图。已安装 `$sakamichi-seichi-map` 时，优先显式调用它；把**公开来源链接、已有截图的说明、希望覆盖的作品范围**交给 Agent，并使用下面的提示词：

```text
请使用 $sakamichi-seichi-map 为「森田ひかる 巡礼マップ」制作 scenes.json 的候选资料。

范围：<列出 MV、Vlog、杂志、博客、活动等>
来源：<粘贴公开链接或本地资料路径>

规则：
1. 只收录公开、适合巡礼且可核验的地点；不推断私人地点、学校、住址、实时行程。
2. 每个候选点必须给出 name、layer、scene_title、scene_ref、scene_note、source_url、source_label、confidence、address 或坐标。
3. 不确定的地点标为 probable / needs-review，不能编造地址、坐标或出处。
4. scene_note 面向普通地图用户，用 1–2 句说明画面和可辨识元素，不写冗长考据。
5. 先输出候选表和待确认问题；在我确认前不要上传图片、不要生成 KML、不要发布地图。
```

人工确认候选表后，第二轮才处理图片、生成文件和导入说明：

```text
请使用 $sakamichi-seichi-map。已确认的 scenes.json 在 <路径>；请按 seichi-maps/README.md 制作 Google My Maps 导入包。

图片规则：仅处理 <列出的、已获许可公开上传的文件/URL>；没有许可或来源不清的图片不要上传，保留出处链接即可。

请完成：
1. 检查 id、图层、地址/坐标、置信度和来源字段；报告缺失项。
2. 将合规图片整理为 original + thumb，建立 R2 映射并上传到本项目的 bucket/prefix。
3. 生成按图层拆分的 KML 和 CSV，解析 XML，检查没有 local:、本机路径和第三方图片热链。
4. 输出导入顺序、变更摘要和待人工确认的点；不要替我把文件导入 Google My Maps。
```

## 生成、验证与导入

现有脚本为 `scripts/build_mymaps_with_images.py`。它要求 scenes JSON、公开文章的本地缓存目录，以及可选的 R2 映射。以森田光项目为例，替换尖括号内容后执行：

```bash
cd /Users/yoru/Documents/SA/项目/sakamichi-tools项目统合/seichi-maps

python3 scripts/build_mymaps_with_images.py \
  --scenes morita-hikaru/morita-hikaru-scenes.json \
  --articles-dir morita-hikaru/sources/articles \
  --output morita-hikaru/my-maps-kml-r2 \
  --title '森田ひかる 巡礼マップ' \
  --group-layers \
  --compact \
  --r2-map morita-hikaru/assets/r2-mirror/r2-image-map.json
```

生成后必须检查：

```bash
python3 -c "from pathlib import Path; from xml.etree import ElementTree as ET; base=Path('morita-hikaru/my-maps-kml-r2'); [ET.parse(p) for p in (base/'kml-with-images').glob('*.kml')]; print('parsed ok')"
rg -n 'local:|/Users/|livedoor\.blogimg|Image [0-9]+|原图' morita-hikaru/my-maps-kml-r2/kml-with-images
```

第二条命令没有输出才正常。正式导入时，在 Google My Maps 中按 `my-maps-kml-r2/kml-with-images/` 的文件顺序逐层导入；不要用总 KML 覆盖整张地图。导入后人工检查每层的位置、弹窗图片、简介、来源链接和图层顺序。

## 交付前清单

- [ ] 不含私人或敏感地点，所有点都有可追溯公开来源。
- [ ] 每个点都有唯一 `id`、作品图层、简短简介、置信度和地址/坐标。
- [ ] `needs-review` / `probable` 没有伪装成已确认事实。
- [ ] 图片已获许可、已压缩去元数据，并通过本项目 R2 URL 访问。
- [ ] KML 可解析，且不存在 `local:`、本机路径或第三方图片热链。
- [ ] KML/CSV/zip 都由 JSON 重新生成；只将分层 KML 导入 My Maps。
