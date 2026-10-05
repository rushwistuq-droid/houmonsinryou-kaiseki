#!/usr/bin/env bash
# homemedical-quality-and-score へ push する補助スクリプト
set -euo pipefail

TARGET_REPO="rushwistuq-droid/homemedical-quality-and-score"
TARGET_URL="https://github.com/${TARGET_REPO}.git"
REMOTE_NAME="homemedical"
SOURCE_BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
TARGET_BRANCH="${2:-main}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Push to ${TARGET_REPO} ==="
echo "Source branch: ${SOURCE_BRANCH}"
echo "Target branch: ${TARGET_BRANCH}"
echo ""

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not a git repository" >&2
  exit 1
fi

if git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
  echo "Remote '${REMOTE_NAME}' already exists:"
  git remote get-url "$REMOTE_NAME"
else
  echo "Adding remote '${REMOTE_NAME}' -> ${TARGET_URL}"
  git remote add "$REMOTE_NAME" "$TARGET_URL"
fi

echo ""
echo "Pushing ${SOURCE_BRANCH} -> ${REMOTE_NAME}/${TARGET_BRANCH} ..."
if git push -u "$REMOTE_NAME" "${SOURCE_BRANCH}:${TARGET_BRANCH}"; then
  echo ""
  echo "Done."
  echo "Repository: https://github.com/${TARGET_REPO}"
  echo ""
  echo "Next steps:"
  echo "  1. Clone: git clone ${TARGET_URL}"
  echo "  2. Restore confidential YAML (see docs/MIGRATION.md)"
  echo "  3. Run: cd home_visit_demand && pip install -r requirements.txt"
  echo "        PYTHONPATH=src python3 scripts/run_hq_pipeline.py"
else
  echo ""
  echo "Push failed. Common fixes:" >&2
  echo "  - Create empty repo first: https://github.com/new?name=homemedical-quality-and-score" >&2
  echo "  - Check GitHub token / SSH key permissions" >&2
  exit 1
fi
