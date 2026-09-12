# 山川宇衣 My Maps KML 导入说明

优先使用 `kml-with-images/` 里的 KML 文件。每个 KML 对应一个 My Maps 图层，地点说明里包含图片预览和出典。

不要把 `yamakawa-ui-all_with_images.kml` 当正式版一次性导入；它适合预览，但后续维护图层不方便。

My Maps 单张地图最多 10 个图层，这版整理成 7 层。

## 导入步骤

1. 打开 Google My Maps，进入你的地图。
2. 按下面顺序逐层点击 `インポート` / `Import`，选择对应的 `.kml` 文件。
3. 如果第一层是空白默认图层，可以直接用它导入第一个 KML。
4. 导入完成后检查弹窗图片。图片预览本身可点击打开原图。

## Layer order

1. `kml-with-images/01_四期生デビューVlog仙台松島.kml` - 四期生デビューVlog仙台松島
2. `kml-with-images/02_Youtube.kml` - Youtube
3. `kml-with-images/03_四期生合宿_山中湖.kml` - 四期生合宿_山中湖
4. `kml-with-images/04_個人PV.kml` - 個人PV
5. `kml-with-images/05_光源MV.kml` - 光源MV
6. `kml-with-images/06_四期生MVそこさく収録.kml` - 四期生MVそこさく収録
7. `kml-with-images/07_MSG&雑誌&Blog.kml` - MSG&雑誌&Blog

## CSV 备份

`mymaps-import-with-images/` 是 CSV 备份。CSV 适合普通地点导入，但图片通常只会作为链接字段，不如 KML 弹窗直观。

CSV 导入时，位置列选 `Location`，标题列选 `Name`。
