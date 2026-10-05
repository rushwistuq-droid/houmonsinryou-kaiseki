#!/usr/bin/env bash
# 引き継ぎ用 zip を作成する
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ZIP_NAME="${1:-homemedical-quality-and-score-handover.zip}"
OUT_DIR="${2:-/opt/cursor/artifacts}"
mkdir -p "$OUT_DIR"
OUT_PATH="$OUT_DIR/$ZIP_NAME"

# 一時ディレクトリにコピー（.git 等を除外）
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DEST="$TMP/homemedical-quality-and-score"
mkdir -p "$DEST"

tar -C "$ROOT" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='*.egg-info' \
  --exclude='.DS_Store' \
  --exclude='homemedical-quality-and-score-handover.zip' \
  --exclude='wakasa-home-visit-demand-handover.zip' \
  --exclude='home_visit_demand/data/confidential' \
  -cf - . | tar -C "$DEST" -xf -

# 機密は example のみ同梱（confidential/ 本体は gitignore のため除外済み）
cat > "$TMP/homemedical-quality-and-score/DOWNLOAD_README.txt" << 'EOF'
homemedical-quality-and-score 引き継ぎパッケージ
============================================

【含まれるもの】
- home_visit_demand/ 一式（ソース・加工データ・成果物・引き継ぎ資料）
- docs/MIGRATION.md
- scripts/push_to_homemedical_repo.sh

【含まれないもの】
- data/confidential/ （機密実績。templates/ から復元してください）
- .git 履歴

【使い方】
1. 任意の場所に unzip
2. cd homemedical-quality-and-score/home_visit_demand
3. mkdir -p data/confidential
   cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
   cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml
4. pip install -r requirements.txt
5. PYTHONPATH=src python3 scripts/run_hq_pipeline.py

詳細: home_visit_demand/docs/HANDOVER.md
EOF

(cd "$TMP" && zip -r -q "$OUT_PATH" homemedical-quality-and-score)

# ワークスペースルートにもコピー（ローカル参照用）
cp "$OUT_PATH" "$ROOT/$ZIP_NAME"

echo "Created: $OUT_PATH"
echo "Copy:    $ROOT/$ZIP_NAME"
ls -lh "$OUT_PATH"
