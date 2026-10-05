# 訪問診療・居宅患者数 地域推定エンジン（高精度版）

クリニック住所から半径8km圏の**居宅訪問診療患者数**を、公的統計に基づき推計します。本部説明用に手法・出典・品質フラグをレポート出力します。

## すぐ使う

```bash
cd home_visit_demand
pip install -r requirements.txt
python3 scripts/download_raw_data.py         # 原本の再取得（任意）
python3 scripts/build_v2_datasets.py          # 初回・データ更新時
PYTHONPATH=src python3 -m home_visit_demand "埼玉県所沢市若狭4-2468-31"
```

緯度経度指定:

```bash
PYTHONPATH=src python3 -m home_visit_demand "所沢" --lat 35.805 --lon 139.455
```

旧ロジック（市区町村代表点）:

```bash
PYTHONPATH=src python3 -m home_visit_demand "..." --legacy
```

## 高精度版でやっていること

| # | 改善 | 内容 |
|---|------|------|
| 1 | メッシュ人口 | 令和2年国勢調査 1/4メッシュ（約250m）で半径円と交差集計 |
| 2 | 5歳階級・将来人口 | 社人研市区町村5歳階級（2020→2025伸び率）でスケール |
| 3 | 都道府県別受療率 | NDBを**居宅/施設で別強度**補正（施設が多い都心で居宅を過大推計しない） |
| 4 | 施設実在 | 介護情報公表システムの入居系事業所（座標・定員）を圏内集計 |
| 5 | 同一建物の分解 | 施設由来と集合住宅居宅を分離 |
| 6 | ポリゴン交差モジュール | `polygons.py`（shapely利用時は面積交差、無ければbbox近似） |
| 7 | 実績キャリブレーション | `scripts/calibrate.py` + YAMLで実績÷推計の縮小推定 |

## 出力の見方（本部定義）

| 指標 | 意味 | 使い方 |
|------|------|--------|
| **居宅市場規模** | 半径圏の居宅訪問診療需要（他院含む） | 出店・ポテンシャル判断の母数 |
| **居宅獲得率** | 自院実績居宅 ÷ 居宅市場規模 | 競合下の取れ高。市場規模には掛けない |
| **施設市場需要** | 圏内入居系に由来する需要 | 参考。契約施設数の説明には使わない |
| **施設契約KPI** | 自院が契約・担当する施設の実績患者 | 施設はこちらで評価（パネル内構成比） |
| **ユニオン市場** | グループ各院圏域の重複除去後需要 | グループ全体のポテンシャル |
| **排他的市場** | 当該院が最寄りのメッシュ需要 | 院間カニバリゼーション把握 |

```bash
# 13院の本部パイプライン（在支診競合・重複・感度・アクション・主担当マップ・浦和軌跡）
PYTHONPATH=src python3 scripts/build_competitors.py    # 初回
PYTHONPATH=src python3 scripts/build_zaishishin.py     # 厚生局在支診（初回・更新時）
PYTHONPATH=src python3 scripts/run_hq_pipeline.py
# → examples/wakasa_hq_dashboard.html
# → examples/mitaka_cluster_ownership_map.html
# → examples/urawa_ramp_tracking.txt
```

運用ルール（半径・KPI・施設）: [`docs/HQ_OPERATING_RULES.md`](docs/HQ_OPERATING_RULES.md)

**成果サマリー資料（本部向け）**: [`docs/HQ_BRIEFING_2026-07.md`](docs/HQ_BRIEFING_2026-07.md) / [`examples/wakasa_hq_briefing.html`](examples/wakasa_hq_briefing.html)

**引き継ぎ資料（新エージェント向け）**: [`docs/HANDOVER.md`](docs/HANDOVER.md)

## 実績キャリブレーション

```bash
# data/processed/calibration_template.yaml をコピーして実績を記入
PYTHONPATH=src python3 scripts/calibrate.py path/to/actuals.yaml
# → data/processed/calibration.yaml に係数が出力される
```

## データ出典

- 厚労省 第10回NDBオープンデータ（在宅医療・性年齢/都道府県）
- 厚労省 社会医療診療行為別統計（2023年）
- 総務省 令和2年国勢調査 地域メッシュ統計 T001102
- 社人研 地域別将来推計人口（令和5年推計）市区町村5歳階級
- 厚労省 介護サービス情報公表システム オープンデータ
- 厚労省 医療情報ネット オープンデータ（診療所・座標突合用）
- 関東信越厚生局 届出受理医療機関名簿（在宅療養支援診療所）
- OpenStreetMap Nominatim / Wikidata

入手元の詳細は `data/SOURCES.md`。

## テスト

```bash
PYTHONPATH=src python3 -m unittest tests.test_estimator tests.test_precision tests.test_hq_analysis tests.test_actions_competition -v
```

## ディレクトリ

```text
home_visit_demand/
  data/mesh_zips/          # 全都道府県メッシュ（再生成用）
  data/ipss_age_raw/       # 社人研5歳階級
  data/facilities_raw/     # 介護情報公表CSV
  data/processed/          # 推定用加工データ
  scripts/build_v2_datasets.py
  scripts/calibrate.py
  src/home_visit_demand/
    precision.py           # 高精度エンジン
    estimator.py           # 旧ロジック
    polygons.py            # ポリゴン交差
  examples/
```
