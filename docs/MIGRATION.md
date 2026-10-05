# 移行手順 — `homemedical-quality-and-score` リポジトリへ引き継ぎ

**移行元**: `github.com/rushwistuq-droid/---`  
**移行先**: `github.com/rushwistuq-droid/homemedical-quality-and-score`  
**移行内容**: `home_visit_demand/` 一式 + 引き継ぎ資料 + 加工済みデータ（約 17MB）

---

## 事前確認

移行先リポジトリに含まれるもの:

- ソースコード（`src/`, `scripts/`, `tests/`）
- 加工済みデータ（`data/processed/*.gz` 等）
- 成果物（`examples/`）
- 引き継ぎ資料（`docs/HANDOVER.md` 等）
- 実績復元用テンプレート（`data/templates/`）

**git に含まれないもの**（移行後も同様）:

- `data/confidential/` — 機密実績（テンプレートから復元）
- `data/mesh_zips/` 等 — 原本（`build_v2_datasets.py` で再取得可）

---

## 手順 A — GitHub 上で空リポジトリを作成して push（推奨）

### 1. GitHub でリポジトリを作成

1. https://github.com/new を開く
2. Repository name: **`homemedical-quality-and-score`**
3. Owner: **`rushwistuq-droid`**
4. **空のまま作成**（README / .gitignore / license は追加しない）
5. Create repository

### 2. ローカルから push

移行元リポジトリを clone 済みの場合:

```bash
cd /path/to/---   # 旧リポジトリのルート

# 移行用リモートを追加
git remote add homemedical https://github.com/rushwistuq-droid/homemedical-quality-and-score.git

# main ブランチとして push（最新の作業内容）
git push homemedical cursor/home-visit-patient-estimation-28cb:main
```

または、付属スクリプトを使う:

```bash
bash scripts/push_to_homemedical_repo.sh
```

### 3. 移行先で確認

```bash
git clone https://github.com/rushwistuq-droid/homemedical-quality-and-score.git
cd homemedical-quality-and-score/home_visit_demand

mkdir -p data/confidential
cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml

pip install -r requirements.txt
PYTHONPATH=src python3 scripts/run_hq_pipeline.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

20 テストが OK、 `examples/wakasa_hq_briefing.html` が更新されれば移行成功です。

---

## 手順 B — 新規 clone から push（旧 repo にアクセスできない場合）

```bash
git clone https://github.com/rushwistuq-droid/---.git wakasa-migrate
cd wakasa-migrate
git checkout cursor/home-visit-patient-estimation-28cb

git remote add homemedical https://github.com/rushwistuq-droid/homemedical-quality-and-score.git
git push homemedical HEAD:main
```

---

## 手順 C — zip で手動移行（Git 操作が難しい場合）

**推奨**: zip をダウンロードして展開するだけで全ファイルを取得できます。

1. `homemedical-quality-and-score-handover.zip` をダウンロード（約 14 MB）  
   - Cursor エージェントの Artifacts から  
   - または clone 後 `bash scripts/create_handover_zip.sh`
2. 詳細: [`docs/DOWNLOAD.md`](DOWNLOAD.md)

```bash
unzip homemedical-quality-and-score-handover.zip
cd homemedical-quality-and-score
git init
git add .
git commit -m "Initial import from handover zip"
git remote add origin https://github.com/rushwistuq-droid/homemedical-quality-and-score.git
git branch -M main
git push -u origin main
```

---

## 手順 D — zip で手動移行（旧手順・GitHub zip ダウンロード）

```bash
unzip ---.zip -d homemedical-quality-and-score
cd homemedical-quality-and-score
git init
git add .
git commit -m "Initial import from home_visit_demand project"
git remote add origin https://github.com/rushwistuq-droid/homemedical-quality-and-score.git
git branch -M main
git push -u origin main
```

---

## 新エージェント（Cursor Cloud Agent）の起動

移行完了後、新エージェントに以下を渡す:

```
リポジトリ rushwistuq-droid/homemedical-quality-and-score を引き継ぐ。

1. home_visit_demand/docs/HANDOVER.md を読む
2. data/templates/ から data/confidential/ に実績 YAML を復元
3. PYTHONPATH=src python3 scripts/run_hq_pipeline.py を実行して成果物を確認
4. 未完了項目（HANDOVER.md 第 12 節）から着手
```

Cursor の Cloud Agent 環境設定では:

- **Repository**: `rushwistuq-droid/homemedical-quality-and-score`
- **Base branch**: `main`

---

## 移行後のディレクトリ構成

```
homemedical-quality-and-score/
├── README.md
├── docs/
│   └── MIGRATION.md          ← 本ファイル
└── home_visit_demand/
    ├── docs/
    │   ├── HANDOVER.md       ← 引き継ぎの本体
    │   ├── HQ_BRIEFING_2026-07.md
    │   └── HQ_OPERATING_RULES.md
    ├── data/
    │   ├── templates/        ← 機密 YAML 復元用
    │   ├── processed/        ← 推計用データ（git 管理）
    │   └── confidential/     ← gitignore（手元で復元）
    ├── src/
    ├── scripts/
    ├── examples/
    └── tests/
```

---

## トラブルシュート

| 症状 | 対処 |
|------|------|
| `actuals not found` | `cp data/templates/*.example.yaml data/confidential/` |
| `ModuleNotFoundError: pandas` | `pip install -r requirements.txt` |
| `mesh_elderly.csv.gz` が無い | `PYTHONPATH=src python3 scripts/build_v2_datasets.py`（時間がかかる） |
| push が 403 | GitHub で repo を先に作成。トークンに repo 書き込み権限を確認 |
| リポジトリが見つからない | 手順 1 で空 repo を作成してから push |

---

## 旧リポジトリとの関係

- 旧 `---` リポジトリの PR #2 は**参照用**として残してよい
- 以降の開発は **`homemedical-quality-and-score` の `main`** を正とする
- 関連ブランチ `cursor/home-care-target-patients-1cfb`（`home_care_target/`）は別系統。必要なら後からサブディレクトリとして追加 import 可能

---

*最終更新: 2026-08-17*
