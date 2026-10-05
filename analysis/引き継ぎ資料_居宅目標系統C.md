# わかさクリニックグループ 在宅・居宅患者分析 引き継ぎ資料

**最終更新**: 2026-08-17  
**対象**: 医療法人元気会 わかさクリニックグループ（13院）  
**リポジトリ**: `github.com/rushwistuq-droid/---`  
**統合ブランチ（作業起点）**: `cursor/home-care-target-patients-1cfb`  
**PR**: [#3 在支診・在支病の精密集計と居宅患者目標ロジック](https://github.com/rushwistuq-droid/---/pull/3)

---

## 0. この資料の使い方（新エージェント向け）

1. **まず本資料を通読**し、3系統のエージェント作業と統合方針を把握する。
2. ブランチ `cursor/home-care-target-patients-1cfb` を checkout する（`main` より大幅に先行）。
3. 機密実績データ `analysis/confidential/` をローカルに配置する（gitignore のためリポジトリには含まれない）。
4. 現状確認:

```bash
PYTHONPATH=home_care_target/src:home_visit_demand/src \
  python3 -m home_care_target.cli --dashboard

PYTHONPATH=home_care_target/src:home_visit_demand/src \
  python3 -m unittest discover -s home_care_target/tests -v
```

5. 詳細成果は `analysis/わかさ_居宅患者目標_成果資料.md` と PDF（`analysis/artifacts/`）を参照。

---

## 1. プロジェクト概要

### 目的

在宅療養支援診療所（在支診）・在宅療養支援病院（在支病）の**供給**と、地域**居宅需要**を公的データで推計し、13院ごとの **居宅患者目標・獲得KPI・実務KPI** を算出。実績患者数との突合、院別アクション設計まで接続する。

### 分析前提

| 項目 | 値 |
|------|-----|
| 対象院 | 13院（本院〜浦和。WA CLINIC は訪問診療対象外） |
| 標準半径 | **8km**（5km=コア、10km=広域補助は需要側で使用） |
| 実績基準日 | **2026-07**（ユーザー提供・施設/居宅人数） |
| 経営の本命KPI | **実務KPI**（成熟院=実績+増分/居宅シフト） |
| 参照KPI | **公平シェアKPI**（競合按分の獲得目標） |

### 経営結論（要約）

- 成熟院は公平シェアを大幅超過。**「獲得KPI未達」ではなく居宅比率シフト**が本命課題。
- **施設偏重ブロック**（本院・所沢・ひばり・石神井・三鷹・高円寺）が最大レバレッジ。
- **市川**は競合相対的に緩く、居宅純増余地あり（実務KPI 83）。
- **浦和**は2026-04開院・開院3ヶ月。**優先対象外**（立ち上がり軌跡のみ監視）。
- **北多摩北部**の居宅開拓優先順位: **東久留米 ＞ 清瀬 ＞ 西東京**。

---

## 2. 複数AIエージェントの作業整理

データ・ロジック・資料が3系統の Cloud Agent / ブランチに分散している。**本流は `home-care-target-patients-1cfb`**。

| # | エージェント名（推定） | ブランチ | 主な成果 | 統合状況 |
|---|------------------------|----------|----------|----------|
| 1 | 訪問診療地域要因分析 | `cursor/wakasa-clinic-regional-analysis-853a` | 13院8km圏の地域比較レポート、開院日、performance_analysis | **未マージ**（参考資料として残存） |
| 2 | 地域居宅患者数推定 | `cursor/home-visit-patient-estimation-28cb` | `home_visit_demand/` 需要エンジン、HQ briefing、メッシュ精度、主担当マップ | **部分統合**（需要モジュールは本流に存在、HQ成果物は別ブランチのみ） |
| 3 | 在宅患者目標計算 | `cursor/home-care-target-patients-1cfb` | `home_care_target/` 供給・KPI・実績突合・ダッシュボード | **本流** |

### 方針

```
需要（home_visit_demand）  ──┐
                              ├──→ home_care_target（供給・目標・実績突合・経営KPI）
供給・競合（home_care_target）─┘
```

- **需要推計**: `home_visit_demand/`（NDB年齢別 × 社人研人口）
- **供給・目標・実績**: `home_care_target/`（在支診/在支病施設点、競合重み、実務KPI）
- 初期地域比較（ブランチ1）は経営背景の説明用。数値の最新版は本流を優先。

---

## 3. ユーザーからの依頼と対応状況

### 3.1 精度強化（1〜7） — ✅ 完了

| # | 改善項目 | 実装場所 |
|---|----------|----------|
| 1 | 年齢・地域別需要 | NDB年齢別 × 社人研2025人口、都道府県居宅シェア |
| 2 | 施設点競合 | JMAP + GSIジオコード（約2,418件） |
| 3 | 地域別居宅シェア | NDB都道府県別（東京≈55%） |
| 4 | 病院ウェイト | 医療施設調査 訪問件数/施設比 |
| 5 | 円交差キャッチメント | 市区町村等面積円 × 半径円交差 |
| 6 | 能力ティア | standard / active / specialty / enhanced |
| 7 | グループ重複按分 | 16km以内の自グループ院で需要を距離逆数按分 |

### 3.2 競合加味の獲得KPI（v0.3→v0.4） — ✅ 完了

```
effective = 機能強化型×1.0 + 従来型×0.35 + 在支病×病院ウェイト + 訪問実施軽加算(0.08/在支診)
competitive_home = 居宅需要 / effective
acquisition_target = clip(competitive × 1.35, 能力/FTE上限)
```

### 3.3 実績患者数の取り込みと突合 — ✅ 完了（機密はローカル）

- 機密: `analysis/confidential/wakasa_patient_actuals.yaml`（gitignore）
- 公開: `home_care_target/data/processed/actuals_vs_acquisition_public.json`

### 3.4 次ステップ1〜5 — ✅ 完了

| # | 内容 | CLI / モジュール |
|---|------|------------------|
| 1 | 実績突合 | `--compare-actuals`, `actuals_compare.py` |
| 2 | 獲得KPIを経営3本柱に固定 | `--dashboard`, `dashboard.py` |
| 3 | 機能強化型重み + 訪問実施軽加算 | `acquisition.py`, `enrich_enhanced_flags.py` |
| 4 | 院ID → 需要+KPI一発 | `--clinic 院名` |
| 5 | 院別アクション（紹介経路・月次新規） | `--actions`, `actions.py`, `referral.py` |

### 3.5 成熟院向け実務KPI・居宅ミックス（v0.5） — ✅ 完了

- **実務KPI（本命）**: 成熟院=実績+年次増分/居宅シフト、未成熟=公平シェア
- **居宅ミックス**: 目標比40%、伸長50%。施設偏重院を優先
- **浦和**: `new_clinics_ignore_priority` で優先対象外
- **自グループ除外**: わかさ/元気会を競合カウントから除外
- **機能強化型**: JMAP type 1/2 で1,104件にフラグ

### 3.6 成果資料・PDF — ✅ 完了

| ファイル | 内容 |
|----------|------|
| `analysis/わかさ_居宅患者目標_成果資料.md` | 経営向け成果サマリ |
| `analysis/北多摩北部3市_居宅開拓比較.md` | 西東京・清瀬・東久留米比較 |
| `analysis/artifacts/wakasa_home_care_target_brief.pdf` | スマホ向けPDF |
| `analysis/artifacts/nishitama_hokubu_home_opportunity.pdf` | 北多摩PDF |

### 3.7 未完了・次にやるとよいこと

| 優先 | 項目 | 詳細 |
|------|------|------|
| 高 | 機密データの再配置 | `analysis/confidential/` が無い環境ではダッシュボードが「実績未登録」になる |
| 高 | 3ブランチのマージ整理 | HQ briefing、主担当マップ、開院日YAML等が未統合 |
| 中 | 紹介経路実績の入力 | `referral_funnel.yaml` はテンプレのみ（未入力） |
| 中 | 清瀬市人口データ修正 | `wakasa_demo_data.py` の清瀬は古い推計。`municipalities.json` は正確 |
| 低 | テスト1件の修正 | 実績未登録時 `test_actions_deprioritize_urawa` が失敗 |

---

## 4. リポジトリ構造

```
/
├── README.md
├── .gitignore                         # analysis/confidential/, **/confidential/**
│
├── analysis/
│   ├── 引き継ぎ資料.md                 # ★本資料
│   ├── わかさ_居宅患者目標_成果資料.md
│   ├── 北多摩北部3市_居宅開拓比較.md
│   ├── artifacts/                     # 公開PDF
│   │   ├── wakasa_home_care_target_brief.pdf
│   │   ├── nishitama_hokubu_home_opportunity.pdf
│   │   └── わかさ_居宅患者目標_成果資料.pdf
│   └── confidential/                  # ★gitignore（要ローカル配置）
│       ├── wakasa_patient_actuals.yaml
│       ├── actuals_vs_acquisition.json
│       ├── management_dashboard.json
│       ├── clinic_action_plans.json
│       └── referral_funnel.yaml
│
├── home_care_target/                  # ★本流：供給・KPI・実績突合
│   ├── README.md
│   ├── src/home_care_target/
│   │   ├── pipeline.py                # 院分析一括
│   │   ├── acquisition.py             # 獲得KPI（公平シェア）
│   │   ├── growth.py                  # 実務KPI・居宅ミックス
│   │   ├── dashboard.py               # 経営3本柱
│   │   ├── actions.py                 # 院別アクション
│   │   ├── referral.py                # 紹介経路接続
│   │   ├── actuals_compare.py         # 実績突合
│   │   ├── facilities.py              # 施設点・自グループ除外
│   │   ├── demand.py                # 需要（home_visit_demand連携）
│   │   ├── catchment.py, geometry.py, targets.py
│   │   ├── wakasa_demo_data.py        # 13院座標・人口・FTE
│   │   └── cli.py
│   ├── data/
│   │   ├── raw/                       # e-Stat, NDB, 医療施設調査CSV
│   │   ├── processed/                 # 正規化JSON、施設点、公開サマリ
│   │   └── templates/referral_funnel.example.yaml
│   ├── scripts/
│   │   ├── build_accuracy_datasets.py
│   │   ├── enrich_enhanced_flags.py
│   │   ├── expand_saitama_facilities.py
│   │   └── compare_actuals.py
│   └── tests/                         # 32 unit tests（1件要修正）
│
└── home_visit_demand/                 # 需要エンジン
    ├── README.md, data/SOURCES.md
    ├── src/home_visit_demand/         # estimator, cli
    ├── data/processed/                # municipalities.json, visit_rates
    └── scripts/build_datasets.py
```

---

## 5. 13院実績とKPI（2026-07）

### 5.1 実績患者数（ユーザー提供・機密）

施設 / 居宅 の順:

| 院 | 施設 | 居宅 | 居宅比 |
|----|------|------|--------|
| 本院 | 1148 | 509 | 31% |
| 所沢 | 611 | 205 | 25% |
| 石神井公園 | 310 | 103 | 25% |
| ひばりが丘 | 393 | 122 | 24% |
| 三鷹 | 187 | 85 | 31% |
| 調布 | 152 | 176 | 54% |
| 府中 | 281 | 162 | 37% |
| 三軒茶屋 | 188 | 124 | 40% |
| 津田沼 | 142 | 335 | 70% |
| 西日暮里 | 35 | 95 | 73% |
| 高円寺 | 172 | 80 | 32% |
| 市川 | 45 | 59 | 57% |
| 浦和 | 0 | 14 | 100% |

### 5.2 実務KPI・状態（v0.5・公開JSONより）

| 院 | 実務KPI | 公平シェア | 状態 | 居宅ミックス | 競合 |
|----|---------|------------|------|--------------|------|
| 本院 | 509 | 36 | 居宅シフト要 | 施設偏重 | 高 |
| 所沢 | 205 | 40 | 居宅シフト要 | 施設偏重 | 高 |
| ひばりが丘 | 122 | 26 | 居宅シフト要 | 施設偏重 | 非常に高 |
| 石神井公園 | 103 | 25 | 居宅シフト要 | 施設偏重 | 非常に高 |
| 三鷹 | 90 | 22 | 居宅シフト要 | 施設偏重 | 非常に高 |
| 府中 | 162 | 47 | 伸長以上 | 標準 | 中 |
| 調布 | 176 | 23 | 伸長以上 | 居宅寄り | 非常に高 |
| 三軒茶屋 | 124 | 24 | 伸長以上 | 標準 | 非常に高 |
| 津田沼 | 335 | 38 | 伸長以上 | 居宅寄り | 高 |
| 西日暮里 | 95 | 36 | 実務KPI達成 | 居宅寄り | 高 |
| 高円寺 | 90 | 27 | 居宅シフト要 | 施設偏重 | 非常に高 |
| 市川 | 83 | 58 | 実務KPI未達 | 居宅寄り | 中 |
| 浦和 | 38 | 28 | 開院初期（対象外） | 居宅寄り | 非常に高 |

### 5.3 優先アクション（12ヶ月）

| 優先 | 院 | 論点 | 居宅シフトギャップ | 月次目安 |
|------|-----|------|-------------------|----------|
| 1 | 本院 | 31%→40% | 154 | 12.8人/月 |
| 2 | 所沢 | 25%→40% | 121 | 10.1 |
| 3 | ひばりが丘 | 24%→40% | 84 | 7.0 |
| 4 | 石神井公園 | 25%→40% | 62 | 5.2 |
| 5 | 三鷹 | 31%→40% | 24 | 2.0 |
| 6 | 高円寺 | 32%→40% | 21 | 1.8 |
| 7 | 市川 | 居宅純増 | — | 2.0人/月 |

---

## 6. 指標定義

### 6.1 経営3本柱

| 指標 | 役割 | 説明 |
|------|------|------|
| **実務KPI** | 本命・短期目標 | 成熟院：実績＋年次増分、または居宅比シフト後の居宅人数 |
| **公平シェアKPI** | 参照 | 地域居宅需要 ÷ 実効競合 × 野心度 |
| **能力上限** | 天井 | specialty水準・医師FTEから見た居宅上限 |
| **居宅ミックス** | 戦略 | 居宅/(居宅+施設)。目標比40%、伸長50% |

### 6.2 実効競合

```
実効ユニット =
  機能強化型在支診 × 1.0
  + 従来型在支診 × 0.35
  + 在支病 × 都道府県別病院ウェイト
  + 非在支の訪問実施診 × 0.08
```

- 機能強化型: JMAP施設単位区分（type 1/2）→ 1,104件
- 自グループ（わかさ/元気会）: 競合から除外

### 6.3 需要側（home_visit_demand）の指標

| 指標 | 意味 |
|------|------|
| 居宅市場規模 | 半径圏の居宅需要（他院含む） |
| 居宅獲得率 | 自院実績居宅 ÷ 居宅市場規模 |
| ユニオン市場 | グループ圏域重複除去後の需要 |
| 排他的居宅市場 | 当該院が最寄りメッシュの需要 |

---

## 7. データソースと主要ファイル

### 7.1 公的データ

| データ | 出所 | 格納先 |
|--------|------|--------|
| 在支診数・受け持ち患者 | 厚労省 令和5年医療施設調査 | `home_care_target/data/raw/` |
| 在支病届出 | 厚労省保険局 | 同上 |
| 施設点・機能強化型 | JMAP + 国土地理院 | `facility_points.json` |
| 年齢別受療率・居宅シェア | 第10回NDB | `home_visit_demand/data/` |
| 病院ウェイト | 医療施設調査 訪問件数 | `hospital_visit_weights.json` |
| 人口 | 社人研 2025年推計 | `municipalities.json` |
| 厚生局在支診 | 関東信越厚生局名簿 | `home-visit-patient-estimation-28cb` ブランチのみ |

### 7.2 主要 processed ファイル

| ファイル | 内容 |
|----------|------|
| `facility_points.json` | 在支診/在支病 2,418件 |
| `municipal_home_support_facilities.json` | 市区町村別在支診/在支病数 |
| `prefecture_home_shares.json` | NDB都道府県別居宅シェア |
| `hospital_visit_weights.json` | 病院ウェイト（東京1.21等） |
| `mhlw_constants.json` | 能力ティア、競合重み、growth_kpi設定 |
| `actuals_vs_acquisition_public.json` | 公開用実績突合サマリ |
| `management_dashboard_public.json` | 公開用ダッシュボード |
| `clinic_action_plans_public.json` | 公開用アクション |

---

## 8. CLI 実行方法

```bash
export PYTHONPATH=home_care_target/src:home_visit_demand/src

# 全院一覧
python3 -m home_care_target.cli

# 1院詳細
python3 -m home_care_target.cli --clinic ひばりが丘

# 経営ダッシュボード
python3 -m home_care_target.cli --dashboard
python3 -m home_care_target.cli --dashboard --write-outputs

# 院別アクション（12ヶ月）
python3 -m home_care_target.cli --actions --months 12

# 実績突合
python3 -m home_care_target.cli --compare-actuals
python3 home_care_target/scripts/compare_actuals.py

# テスト
python3 -m unittest discover -s home_care_target/tests -v
```

### 需要側のみ（単院推計）

```bash
PYTHONPATH=home_visit_demand/src \
  python3 -m home_visit_demand "住所" --lat ... --lon ...
```

---

## 9. 他ブランチの独自成果物（未統合）

### 9.1 `cursor/wakasa-clinic-regional-analysis-853a`

| ファイル | 内容 |
|----------|------|
| `analysis/わかさクリニックグループ_地域比較分析報告書.md` | 13院8km圏の初期地域比較（2026-07-13） |
| `analysis/clinic_opening_dates.yaml` | 各院開院日・戦略世代ラベル |
| `analysis/performance_analysis.py` | 実績×地域要因の分析スクリプト |
| `analysis/wakasa_clinic_regional_analysis.py` | 地域比較の生成スクリプト |

**要点**: 売上格差の主因は地域性。A（努力で伸びやすい）=本院・所沢・津田沼・市川、C（構造的に厳しい）=三軒茶屋・三鷹・高円寺・石神井。

### 9.2 `cursor/home-visit-patient-estimation-28cb`

| ファイル | 内容 |
|----------|------|
| `home_visit_demand/docs/HQ_BRIEFING_2026-07.md` | 本部向け成果サマリ |
| `home_visit_demand/docs/HQ_OPERATING_RULES.md` | 正式運用ルール |
| `home_visit_demand/examples/wakasa_hq_dashboard.html` | 定例ダッシュボード |
| `home_visit_demand/examples/wakasa_action_sheets.txt` | 院別アクションシート |
| `home_visit_demand/examples/mitaka_cluster_ownership_map.html` | 三鷹クラスター主担当マップ |
| `home_visit_demand/examples/urawa_ramp_tracking.html` | 浦和立ち上げ軌跡 |
| `home_visit_demand/scripts/run_hq_pipeline.py` | 全成果再生成 |

**要点**: グループユニオン市場≈73,200人（単純合算111,700の重複除去後）。市川は獲得率下回り→居宅開拓優先。

---

## 10. 機密データの配置手順

`analysis/confidential/` は gitignore のため、新環境では手動配置が必要。

### 10.1 `wakasa_patient_actuals.yaml`（必須）

```yaml
as_of: "2026-07"
clinics:
  - alias: 本院
    facility_patients: 1148
    home_patients: 509
  - alias: 所沢
    facility_patients: 611
    home_patients: 205
  # ... 以下13院（上記 §5.1 参照）
  - alias: 浦和
    facility_patients: 0
    home_patients: 14
```

### 10.2 `referral_funnel.yaml`（任意・未入力）

テンプレ: `home_care_target/data/templates/referral_funnel.example.yaml`  
CM/病院/訪看の月次新規を記入すると、アクションが実数ベースに切り替わる。

---

## 11. 設計上の重要ポイント

1. **獲得KPI vs 実務KPI**: 成熟院は公平シェアを既に超過。経営本命は `growth.py` の実務KPI。
2. **施設偏重 ≠ 人数不足**: 本院等は総患者数は十分だが居宅構成が薄い（31%等）。
3. **ひばりが丘**: 北多摩開拓は東久留米優先（在支診密度最低、ひばりから1.6km）。
4. **三鷹クラスター**: 石神井・ひばり・三鷹・調布・府中・高円寺で係争メッシュ≈94万人。主担当分担が必要。
5. **浦和**: 2026-04開院。5km獲得率を短期KPIとし、帯到達前に施設偏重へ寄せない。

---

## 12. 各院開院日（参考・ブランチ1より）

| 院 | 開設 | 備考 |
|----|------|------|
| 本院 | 2000-01 | 在宅医療部門 2014 |
| 所沢 | 2021 | |
| 石神井公園 | 2022-02 | |
| ひばりが丘 / 三鷹 | 2022-08 | |
| 府中 / 調布 | 2023-04 | 居宅重視への転換期起点 |
| 三軒茶屋 | 2023-08 | |
| 津田沼 | 2024-04 | |
| 西日暮里 / 高円寺 | 2025-04 | |
| 市川 | 2025-11 | |
| 浦和 | 2026-04 | 開院3ヶ月 |

---

## 13. Git 履歴（本流ブランチ）

```
747c6c4 Add consultant comparison of Nishitokyo, Kiyose, Higashikurume home opportunity
91fd839 Add phone-friendly PDF brief of home-care target results
f7a620e Add Japanese summary brief of home-care target deliverables
3826c2b Add mature growth KPI, home-mix shift, enhanced flags, and referral hooks
c7e30d6 Compare branch actuals to acquisition KPI and expand 浦和 catchment
16478ce Add competition-weighted patient acquisition KPI
940e110 Improve target accuracy with NDB demand, facility points, and overlap
```

---

## 14. 新エージェントへの推奨プロンプト

```
リポジトリ github.com/rushwistuq-droid/--- の branch cursor/home-care-target-patients-1cfb をベースに作業してください。

【背景】
わかさクリニックグループ13院の在宅・居宅患者分析プロジェクト。
- home_care_target/ = 供給・KPI・実績突合の本流
- home_visit_demand/ = NDB年齢別需要推計
- analysis/引き継ぎ資料.md を最初に読んでください

【現状】
- 実績は analysis/confidential/wakasa_patient_actuals.yaml（gitignore、要配置）
- 成熟院の本命KPIは居宅比率シフト（施設偏重→40%）
- 市川は居宅純増、浦和は開院初期で優先対象外
- 北多摩は東久留米＞清瀬＞西東京

【最初の確認】
PYTHONPATH=home_care_target/src:home_visit_demand/src python3 -m home_care_target.cli --dashboard

【未完了タスク例】
- 3ブランチの成果統合（HQ briefing、開院日YAML、主担当マップ）
- referral_funnel.yaml への紹介経路実績入力
- 清瀬市人口データの demo_data 修正
```

---

## 15. 関連リンク

| リンク | 内容 |
|--------|------|
| [PR #3](https://github.com/rushwistuq-droid/---/pull/3) | 本流PR |
| `analysis/わかさ_居宅患者目標_成果資料.md` | 経営成果資料 |
| `analysis/北多摩北部3市_居宅開拓比較.md` | 地域開拓比較 |
| `home_care_target/README.md` | 技術README |
| `home_visit_demand/README.md` | 需要エンジンREADME |

---

## 改訂履歴

| 日付 | 内容 |
|------|------|
| 2026-08-17 | 初版。3系統エージェント作業・データ・依頼履歴・KPI・未完了タスクを統合 |
