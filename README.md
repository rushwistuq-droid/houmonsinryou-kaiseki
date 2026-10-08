# わかさクリニックグループ 訪問診療 地域・実績分析

理事長面談（2026年秋）に向けて、過去3系統の分析を統合したリポジトリです。

## まず読むもの

| 資料 | 内容 |
|------|------|
| [`briefing/01_データカタログ.md`](briefing/01_データカタログ.md) | 取得済みデータの一覧・信頼度・未取得データ |
| [`briefing/02_指数辞書.md`](briefing/02_指数辞書.md) | これまでの指数と公式採用／廃止の判断 |
| [`briefing/03_分析結果.md`](briefing/03_分析結果.md) | 予測指数の選定・既存院の診断方法・出店候補 |
| [`briefing/04_活用提案.md`](briefing/04_活用提案.md) | 経営での使い方・データ運用の提案 |

## 再計算

```bash
pip install pandas numpy scipy openpyxl pyyaml matplotlib
python3 briefing/scripts/import_monthly_upload.py <院から届いたExcel>   # 月次の患者数・新規・終了を取り込む（機密）
python3 briefing/build_all.py                 # 全指数・図表・Excel（約40秒）
python3 briefing/site_check.py --lat 35.89 --lon 139.79 --name 候補地   # 出店候補地の評価
python3 -m unittest discover -s briefing/tests
```

機密データ（院別の患者数・医師数・月次推移）は `analysis/confidential/` と `home_visit_demand/data/confidential/` に置き、**コミットしない**（`.gitignore` 済み）。復元方法は `analysis/引き継ぎ資料.md` §4。月次データの取り込み方は `briefing/templates/README_monthly_flow.md`。

## ディレクトリ

| パス | 内容 |
|------|------|
| `briefing/` | **統合版**: 指数エンジン・予測モデル・飽和度診断・出店スコア・面談資料 |
| `briefing/output/` | 公開データのみの成果（地域指数、出店候補、地図） |
| `home_visit_demand/` | 系統B: メッシュ人口×NDBの需要推計（データ本体もここ） |
| `home_care_target/` | 系統C: 在支診点データ・居宅目標KPI |
| `analysis/` | 系統A: 初期の地域比較（自治体データに誤りがあるため参考扱い）と引き継ぎ資料 |

## 経緯

PR #1（`analysis/`）・PR #2（`home_visit_demand/`）・PR #3（`home_care_target/`）の3ブランチをこのブランチに統合した。`home_visit_demand/` は新しい PR #2 版を採用している。

## 面談資料（機密）の生成

```bash
python3 briefing/build_all.py
python3 briefing/deck/export_deck_data.py
NODE_PATH=<pptxgenjs の node_modules> node briefing/deck/build_deck.js   # → analysis/confidential/briefing/*.pptx
python3 briefing/deck/build_summary.py                                   # → A4要旨PDF（playwright＋Chromium）
```
出力はすべて `analysis/confidential/briefing/`（Git管理外）。
