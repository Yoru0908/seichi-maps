# 山川宇衣 My Maps KML 导入说明

优先使用 `kml-with-images/` 里的 KML 文件。每个 KML 对应一个 My Maps 图层，地点说明里包含 fumi 图片预览、原图链接和出典。

不要把 `yamakawa-ui-all_with_images.kml` 当正式版一次性导入；它适合预览，但后续维护图层不方便。

My Maps 单张地图最多 10 个图层，这版整理成 7 层。

## 导入步骤

1. 打开 Google My Maps，进入你的地图。
2. 按下面顺序逐层点击 `インポート` / `Import`，选择对应的 `.kml` 文件。
3. 如果第一层是空白默认图层，可以直接用它导入第一个 KML。
4. 导入完成后检查弹窗图片。若 My Maps 没显示热链图片，先点弹窗里的 `原图` 链接查看；之后再考虑把图片迁到 R2 或 Alist。

## Layer order

1. `kml-with-images/01_四期生Vlog_仙台_松島.kml` - 四期生Vlog - 仙台・松島
2. `kml-with-images/02_2026年始Vlog_ソロキャンプ.kml` - 2026年始Vlog・ソロキャンプ
3. `kml-with-images/03_四期生合宿_山中湖.kml` - 四期生合宿 - 山中湖
4. `kml-with-images/04_個人PV.kml` - 個人PV
5. `kml-with-images/05_光源_PV.kml` - 光源 PV
6. `kml-with-images/06_四期生PV_グループMV.kml` - 四期生PV・グループMV
7. `kml-with-images/07_雑誌_Blog_補足.kml` - 雑誌・ブログ・補足

## CSV 备份

`mymaps-import-with-images/` 是 CSV 备份。CSV 适合普通地点导入，但图片通常只会作为链接字段，不如 KML 弹窗直观。

CSV 导入时，位置列选 `Location`，标题列选 `Name`。
