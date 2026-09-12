# 山川宇衣 tag pages coverage audit

Checked pages:

- `p=2`: http://blog.livedoor.jp/fumichen2/tag/%E5%B1%B1%E5%B7%9D%E5%AE%87%E8%A1%A3?p=2
- `p=3`: http://blog.livedoor.jp/fumichen2/tag/%E5%B1%B1%E5%B7%9D%E5%AE%87%E8%A1%A3?p=3
- `p=4`: http://blog.livedoor.jp/fumichen2/tag/%E5%B1%B1%E5%B7%9D%E5%AE%87%E8%A1%A3?p=4

`p=4` has no `rel="next"` link, so the saved tag set ends there.

## Article coverage

All articles from pages 2-4 are represented in `yamakawa-ui-scenes.json`.

| Page | Article ID | Scene count | Title |
|---|---:|---:|---|
| p=2 | 59543470 | 2 | 櫻坂46 山川宇衣 BOMB 2025年11月号写真撮影場所 |
| p=2 | 59536364 | 1 | 櫻坂46 山川宇衣 FLASH 2025.12.02-09 写真撮影場所 |
| p=2 | 59534473 | 1 | 櫻坂46 山川宇衣 週刊ヤングジャンプ 2025 No.48 写真撮影場所 |
| p=2 | 59476386 | 1 | 2025.10.15 櫻坂46 山川宇衣 目移りの秋 blog写真撮影場所 |
| p=2 | 59470718 | 1 | 2025.10.13 櫻坂46 山川宇衣 バターイエローの夏 blog写真撮影場所 |
| p=3 | 59440654 | 1 | 櫻坂46 四期生 ViVi 2025年11月号写真撮影場所 |
| p=3 | 59438651 | 1 | 櫻坂46「Alter ego」PV撮影場所 |
| p=3 | 59429929 | 2 | 2025.09.21 櫻坂46 山川宇衣 羽化 blog写真撮影場所 |
| p=3 | 59416586 | 1 | 櫻坂46 四期生 BLT 2025年11月号写真撮影場所 |
| p=3 | 59394901 | 1 | 櫻坂46 山川宇衣 2025年9月グリーティングカード写真撮影場所 |
| p=4 | 59345419 | 2 | 2025.08.07 櫻坂46 山川宇衣 好きなこと blog写真撮影場所 |
| p=4 | 59344112 | 1 | 櫻坂46 山川宇衣 週刊少年マガジン 2025 No.36+37写真撮影場所 |
| p=4 | 59249136 | 1 | 櫻坂46「死んだふり」PV撮影場所 |
| p=4 | 59195794 | 8 | 櫻坂46 四期生合宿場所 |
| p=4 | 59133579 | 12 | 櫻坂46 山川宇衣 四期生Vlog撮影場所 |

## Intentional exclusions

- `soy casa akikawa` in article `59344112` is not mapped because the source states it is a private residence and should not be registered to a location map.
- `東京ディズニー` in article `59345419` is only a guess, so it is not mapped.
- Active school/campus locations are reference-only or have strict no-entry notes when retained.
- Unidentified indoor studios, suspected lodging, and `不明` locations are not mapped.
