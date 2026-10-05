# 一括ダウンロード（zip）

GitHub 操作やリポジトリ移行が難しい場合、**全ファイルを zip で取得**できます。

## ダウンロード方法

### 方法 1 — Cursor エージェントから（いちばん簡単）

このエージェント実行の **Artifacts** から次のファイルをダウンロード:

| ファイル | サイズ | 内容 |
|----------|--------|------|
| **`homemedical-quality-and-score-handover.zip`** | 約 14 MB | プロジェクト一式 |

### 方法 2 — リポジトリ clone 後に生成

```bash
git clone https://github.com/rushwistuq-droid/---.git
cd ---
git checkout cursor/home-visit-patient-estimation-28cb
bash scripts/create_handover_zip.sh
```

ルートに `homemedical-quality-and-score-handover.zip` が作成されます。

---

## zip の中身

```
homemedical-quality-and-score/
├── DOWNLOAD_README.txt      ← 展開直後に読む
├── README.md
├── docs/
│   ├── MIGRATION.md
│   └── DOWNLOAD.md
├── scripts/
│   ├── create_handover_zip.sh
│   └── push_to_homemedical_repo.sh
└── home_visit_demand/
    ├── docs/HANDOVER.md     ← 引き継ぎの本体
    ├── data/processed/      ← 推計用データ（mesh 等）
    ├── data/templates/      ← 機密実績の復元用
    ├── src/, scripts/, tests/, examples/
    └── ...
```

## 含まれないもの

| 除外 | 理由 | 復元方法 |
|------|------|----------|
| `.git` | 履歴不要 | 新 repo で `git init` |
| `data/confidential/` | 機密（gitignore） | `data/templates/*.example.yaml` をコピー |

---

## 展開後の手順

```bash
unzip homemedical-quality-and-score-handover.zip
cd homemedical-quality-and-score/home_visit_demand

mkdir -p data/confidential
cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml

pip install -r requirements.txt
PYTHONPATH=src python3 scripts/run_hq_pipeline.py
```

### 新リポジトリ `homemedical-quality-and-score` に載せる場合

```bash
cd homemedical-quality-and-score
git init
git add .
git commit -m "Import from handover zip"
git remote add origin https://github.com/rushwistuq-droid/homemedical-quality-and-score.git
git branch -M main
git push -u origin main
```

（GitHub で空リポジトリを先に作成してください）

---

## 新エージェントへの指示（zip 利用時）

```
homemedical-quality-and-score-handover.zip を展開したプロジェクトを引き継ぐ。

1. home_visit_demand/docs/HANDOVER.md を読む
2. data/templates/ から data/confidential/ に YAML を復元
3. PYTHONPATH=src python3 scripts/run_hq_pipeline.py を実行
```
