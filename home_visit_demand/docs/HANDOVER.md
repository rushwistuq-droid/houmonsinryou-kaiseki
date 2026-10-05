# 引き継ぎ資料 — わかさクリニックグループ 訪問診療・地域需要推計

**作成目的**: 複数の AI エージェントに散在していた作業・データ・判断を一箇所に集約し、新エージェントが即座に引き継げるようにする。  
**最終更新**: 2026-08-17  
**対象クライアント**: わかさクリニックグループ（13院）  
**正リポジトリ**: `github.com/rushwistuq-droid/homemedical-quality-and-score`

---

## 0. 新エージェントへの最初の指示（コピペ用）

```
リポジトリ rushwistuq-droid/homemedical-quality-and-score を引き継ぐ。

1. home_visit_demand/docs/HANDOVER.md を最初に読む
2. 続けて docs/HQ_BRIEFING_2026-07.md と docs/HQ_OPERATING_RULES.md を読む
3. 機密実績を復元:
   cd home_visit_demand
   mkdir -p data/confidential
   cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
   cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml
4. 依存関係とパイプライン実行:
   pip install -r requirements.txt
   PYTHONPATH=src python3 scripts/run_hq_pipeline.py
5. 成果物を examples/ で確認（特に wakasa_hq_briefing.html）
```

移行手順: リポジトリルートの `docs/MIGRATION.md`

---

## 1. プロジェクトの目的

**クリニック住所から半径 8km 圏の居宅訪問診療患者数（市場規模）**を公的統計で推計し、**自院実績**と突合して本部の出店・KPI・競合判断に使う分析基盤を構築する。

### 最重要の定義（混同禁止）

| 指標 | 意味 |
|------|------|
| **居宅市場規模** | 半径圏に発生しうる居宅訪問診療需要（**他院含む**）。推計エンジンの出力。 |
| **居宅獲得率** | 自院実績居宅 ÷ 居宅市場規模。**自院の取れ高**。 |
| **施設契約KPI** | 自院が契約・担当する施設の実績患者。施設市場需要との「シェア」は使わない。 |

> 推計値を「自院が取れる人数」と解釈しない。市場規模にキャリブレーション係数を掛けない。

---

## 2. リポジトリ

| 項目 | 値 |
|------|-----|
| **正リポジトリ（移行先）** | `github.com/rushwistuq-droid/homemedical-quality-and-score` |
| メインブランチ | `main` |
| パッケージルート | `home_visit_demand/` |
| 移行手順 | リポジトリルート `docs/MIGRATION.md` |

### 移行元（参照用・開発終了）

| 項目 | 値 |
|------|-----|
| 旧リポジトリ | `github.com/rushwistuq-droid/---` |
| 旧ブランチ | `cursor/home-visit-patient-estimation-28cb` |
| 旧 PR | https://github.com/rushwistuq-droid/---/pull/2 |

### 関連（別 AI・別フェーズ）

| リポジトリ/ブランチ | 内容 | 関係 |
|---------------------|------|------|
| `---` / `cursor/home-care-target-patients-1cfb` | `home_care_target/`（居宅 KPI 目標） | **別系統**。必要なら後から統合 |
| `---` / `cursor/wakasa-clinic-regional-analysis-853a` | 市区町村代表点の簡易分析（v1） | 本プロジェクトに統合済み |

---

## 3. 会話の流れと実施フェーズ

### Phase 1 — 高精度推計エンジン（v2）

- `home_visit_demand/` パッケージ新規作成
- **v2（デフォルト）**: 国勢調査 1/4 メッシュ × 都道府県別 NDB（居宅/施設分離）× 介護情報公表施設 × 同一建物補正
- **v1（legacy）**: 市区町村代表点 + 距離重み（`--legacy` フラグ）

### Phase 2 — 13 院実績突合

- ユーザー提供の 2026-07 実績（施設/居宅）を YAML で受け取り
- `scripts/compare_actuals.py` で市場推計 vs 実績
- **発見**: 東京圏は 8km 市場が 1〜1.5 万人規模 → 獲得率 0.5〜2% でも期待帯内になりうる

### Phase 3 — 本部向け分析パイプライン

1. 指標定義の固定（市場 vs 獲得率 vs 施設 KPI）
2. 圏域重複除去（メッシュ・ユニオン）— 65+ の二重計上 **43%**
3. 期待獲得率帯（密度 + グループ近接 + 競合）
4. 半径感度（5/8/10km）— **標準 8km**
5. 施設 KPI 分離（契約患者・パネル構成比）

### Phase 4 — 外部競合指標の修正

- **当初**: 医療情報ネットの名称/科目近似 → 精度低、ユーザー指摘
- **修正後**: 関東信越厚生局の**在宅療養支援診療所（在支診）**届出受理名簿を主指標
- `scripts/build_zaishishin.py` で埼玉・千葉・東京・神奈川を抽出（座標突合約 70%）

### Phase 5 — 主担当マップ・浦和トラッキング

- 三鷹クラスター（石神井・ひばり・三鷹・調布・府中・高円寺）のメッシュ最寄り院割当
- 浦和の 3/6/12 か月立ち上がり軌跡（`urawa_ramp.yaml` 月次更新）

### Phase 6 — 成果資料

- `docs/HQ_BRIEFING_2026-07.md` + `examples/wakasa_hq_briefing.html`（スマホ向けカード表示）

---

## 4. ユーザー提供データ（2026-07 実績）

**基準月**: 2026-07  
**形式**: 施設患者数 / 居宅患者数（13 院）

| 院 | 施設 | 居宅 |
|----|-----:|-----:|
| 本院 | 1148 | 509 |
| 所沢 | 611 | 205 |
| 石神井公園 | 310 | 103 |
| ひばりが丘 | 393 | 122 |
| 三鷹 | 187 | 85 |
| 調布 | 152 | 176 |
| 府中 | 281 | 162 |
| 三軒茶屋 | 188 | 124 |
| 津田沼 | 142 | 335 |
| 高円寺 | 172 | 80 |
| 西日暮里 | 35 | 95 |
| 市川 | 45 | 59 |
| 浦和 | 0 | 14 |

**保存場所**: `data/confidential/actuals_2026-07.yaml`（gitignore・機密）  
**復元用テンプレート**: `data/templates/actuals_2026-07.example.yaml`

---

## 5. 13 院マスタ（座標・ID）

パイプライン・HQ 分析で使用する `ClinicInput` の定義。

| id | 院名 | lat | lon |
|----|------|-----|-----|
| honin | 本院 | 35.805 | 139.455 |
| tokorozawa | 所沢 | 35.799 | 139.472 |
| hibarigaoka | ひばりが丘 | 35.745 | 139.538 |
| shakujii | 石神井公園 | 35.743 | 139.601 |
| mitaka | 三鷹 | 35.683 | 139.559 |
| chofu | 調布 | 35.652 | 139.543 |
| fuchu | 府中 | 35.669 | 139.477 |
| sangenjaya | 三軒茶屋 | 35.646 | 139.670 |
| tsudanuma | 津田沼 | 35.682 | 140.020 |
| koenji | 高円寺 | 35.705 | 139.649 |
| nishinippori | 西日暮里 | 35.732 | 139.768 |
| ichikawa | 市川 | 35.718 | 139.915 |
| urawa | 浦和 | 35.880526 | 139.641896 |

---

## 6. 主要な数値結果（8km・2026-07 実績基準）

| 項目 | 値 |
|------|-----|
| 単純合算・居宅市場 | 約 **111,720** |
| **ユニオン・居宅市場（重複除去後）** | 約 **73,150** |
| 65+ の二重計上率 | **43.0%** |
| 係争メッシュ高齢者（2 院以上カバー） | 約 **162 万人** |

### 院別ハイライト

| 院 | 居宅市場 | 獲得率 | 期待帯 | 判定 | アクション |
|----|--------:|-------:|--------|------|------------|
| 本院 | 2,269 | **22.4%** | 2.25–9.6% | 上限超 | **横展開** |
| 津田沼 | 2,480 | **13.5%** | 2.25–9.6% | 上限超 | **横展開** |
| 市川 | 8,410 | **0.7%** | 0.75–4% | 下回る | **やる（高）** |
| 浦和 | 2,448 | 0.6% | 2.25–9.6% | 下回る※ | **様子見** |
| 東京圏各院 | 7k–15k | 0.5–2% | 帯内 | — | 在支診 200–400 院 |

※浦和は開院直後。低獲得率は立ち上がり要因として経過観察。

詳細表: `docs/HQ_BRIEFING_2026-07.md` 第 5 節、`examples/wakasa_hq_pipeline_report.txt`

---

## 7. 修正した重要バグ・設計判断

1. **都道府県別受療率**: 居宅/施設を分離しないと東京で居宅を過大推計
2. **IPSS スケール**: mesh/IPSS 絶対比（1.35 キャップ）→ **2020→2025 伸び率**に修正
3. **キャリブレーション**: 市場規模に係数を掛けない（獲得率の参考値のみ）
4. **外部競合**: 名称近似 → **厚生局在支診**に切替（ユーザー指摘反映）
5. **施設評価**: 施設市場需要とのシェアは使わず、契約 KPI + パネル構成比

---

## 8. ディレクトリ構成

```
home_visit_demand/
├── README.md                          # 使い方（技術）
├── docs/
│   ├── HANDOVER.md                    # ★本資料
│   ├── HQ_BRIEFING_2026-07.md         # ★成果サマリー（本部向け）
│   └── HQ_OPERATING_RULES.md          # 正式運用ルール
├── data/
│   ├── templates/                     # 機密 YAML の復元用（git 管理）
│   │   ├── actuals_2026-07.example.yaml
│   │   └── urawa_ramp.example.yaml
│   ├── confidential/                  # gitignore（実績・月次更新）
│   ├── processed/                     # 推定用加工データ（git 管理）
│   │   ├── mesh_elderly.csv.gz
│   │   ├── facilities.csv.gz
│   │   ├── pref_visit_rates.json
│   │   ├── zaishishin.csv.gz
│   │   ├── competitors_home.csv.gz
│   │   └── clinics_all_coords.csv.gz
│   ├── mesh_zips/                     # gitignore（再生成用）
│   └── SOURCES.md
├── src/home_visit_demand/
│   ├── precision.py                   # ★高精度推計エンジン（デフォルト）
│   ├── estimator.py                   # 旧ロジック（--legacy）
│   ├── hq_analysis.py                 # ★本部パイプライン
│   ├── competition.py                 # 在支診競合密度
│   ├── action_sheets.py               # 院別アクションシート
│   ├── ownership_map.py               # 主担当メッシュマップ
│   ├── urawa_tracking.py              # 浦和立ち上がり
│   └── dashboard.py                   # HTML ダッシュボード
├── scripts/
│   ├── build_v2_datasets.py           # データセット再生成
│   ├── build_zaishishin.py            # ★厚生局在支診
│   ├── run_hq_pipeline.py             # ★全成果一括生成
│   └── compare_actuals.py             # 実績突合
├── examples/                          # 出力成果物（再生成可）
│   ├── wakasa_hq_briefing.html        # ★本部向け（スマホ対応）
│   ├── wakasa_hq_dashboard.html
│   ├── wakasa_hq_pipeline_report.txt
│   ├── wakasa_action_sheets.txt
│   ├── mitaka_cluster_ownership_map.html
│   └── urawa_ramp_tracking.html
└── tests/                             # 20 テスト
```

---

## 9. 実行コマンド

```bash
cd home_visit_demand
pip install -r requirements.txt

# 機密実績の復元（初回）
mkdir -p data/confidential
cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml

# データ構築（初回・更新時。processed/ に無い場合は自動実行されることも）
PYTHONPATH=src python3 scripts/build_v2_datasets.py
PYTHONPATH=src python3 scripts/build_competitors.py
PYTHONPATH=src python3 scripts/build_zaishishin.py

# 全成果一括生成
PYTHONPATH=src python3 scripts/run_hq_pipeline.py

# 単院推計
PYTHONPATH=src python3 -m home_visit_demand "住所" --lat ... --lon ...

# 実績突合のみ
PYTHONPATH=src python3 scripts/compare_actuals.py

# テスト（20 件）
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

---

## 10. 成果物の閲覧

### ローカル

```bash
# ブラウザで開く
home_visit_demand/examples/wakasa_hq_briefing.html
```

### GitHub 上（HTML プレビュー）

GitHub の blob ページはコード表示になるため、HTML Preview 経由:

```
https://htmlpreview.github.io/?https://raw.githubusercontent.com/rushwistuq-droid/homemedical-quality-and-score/main/home_visit_demand/examples/wakasa_hq_briefing.html
```

---

## 11. データ出典

| データ | 出典 |
|--------|------|
| NDB 在宅医療 | 厚労省 第 10 回 NDB オープンデータ |
| メッシュ人口 | 令和 2 年国勢調査 地域メッシュ統計 T001102 |
| 将来人口 | 社人研 地域別将来推計人口（5 歳階級） |
| 施設 | 介護サービス情報公表システム |
| **在支診（競合主指標）** | 関東信越厚生局 届出受理医療機関名簿 |
| 診療所座標 | 厚労省 医療情報ネット |

詳細: `data/SOURCES.md`

---

## 12. 未完了・任意改善（優先度順）

ユーザーが挙げた改善のうち **1→2→3 は完了**。以下は任意:

| # | 項目 | 内容 |
|---|------|------|
| 1 | 在支診の未突合座標（約 30%） | 住所ジオコードで埋められる |
| 2 | 契約施設の突合 | 実績施設と介護情報公表の事業所を紐づけ |
| 3 | 県境院の受療率 | 市川など、県別按分の精度向上 |
| 4 | ダッシュボード地図 UI | 現状静的 HTML → Leaflet 等でインタラクティブ化 |
| 5 | 浦和の月次運用 | YAML 更新は運用作業（仕組みは済み） |
| 6 | `home_care_target/` 統合 | 別ブランチの居宅 KPI 目標計算との連携 |

---

## 13. 本部への推奨メッセージ（1 枚）

1. **市場はユニオン、院 KPI は排他＋獲得率**で見る。
2. **標準半径は 8km**。本院・津田沼の強さは 5km コアでも確認。
3. **市川は居宅開拓**、**浦和は立ち上がり軌跡**、**三鷹クラスターは主担当分担**。
4. **施設は契約 KPI**。市場シェアで施設を評価しない。
5. 外部競合は名称近似ではなく **厚生局在支診** を使う。

---

## 14. コミット履歴（本 PR ブランチ）

```
c4a59aa Make HQ briefing HTML mobile-friendly with card layout
bda506b Add HQ briefing pack summarizing current deliverables
f9c46d3 Use Koseikyoku 在支診 data; add ownership map and Urawa ramp
8fec186 Add HQ action sheets, external competition, dashboard, radius rules
db8b79f Add HQ pipeline: overlap union, share bands, radius sensitivity
3edc492 Add Wakasa actuals-vs-model comparison for 13 clinics
1aa8103 Upgrade home-visit demand model to HQ-grade precision
5e63067 Add regional home-visit patient demand estimation engine
```

---

*本資料は複数 AI セッションの作業を統合した引き継ぎ用ドキュメントです。数値の正式版は `run_hq_pipeline.py` 再実行結果を参照してください。*
