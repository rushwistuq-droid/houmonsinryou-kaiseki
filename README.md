# homemedical-quality-and-score

わかさクリニックグループ向けの **訪問診療・地域需要推計** と、今後の **品質・スコアリング** 拡張を行うリポジトリです。

## 含まれるもの

| パス | 内容 |
|------|------|
| [`home_visit_demand/`](home_visit_demand/) | 半径 8km 圏の居宅市場規模推計・本部分析パイプライン（メイン） |
| [`home_visit_demand/docs/HANDOVER.md`](home_visit_demand/docs/HANDOVER.md) | **引き継ぎ資料**（新エージェントはここから） |
| [`home_visit_demand/docs/HQ_BRIEFING_2026-07.md`](home_visit_demand/docs/HQ_BRIEFING_2026-07.md) | 本部向け成果サマリー |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | 旧リポジトリからの移行手順 |

## クイックスタート

```bash
cd home_visit_demand
pip install -r requirements.txt

# 機密実績の復元（初回のみ）
mkdir -p data/confidential
cp data/templates/actuals_2026-07.example.yaml data/confidential/actuals_2026-07.yaml
cp data/templates/urawa_ramp.example.yaml data/confidential/urawa_ramp.yaml

# 全成果一括生成
PYTHONPATH=src python3 scripts/run_hq_pipeline.py
```

## 旧リポジトリから移行した場合

移行元: `rushwistuq-droid/---`（ブランチ `cursor/home-visit-patient-estimation-28cb`）

手順: [`docs/MIGRATION.md`](docs/MIGRATION.md)

## 一括ダウンロード（zip）

Git 操作なしで全ファイルを取得する場合:

1. **Cursor エージェント実行画面**の Artifacts / 添付から  
   `homemedical-quality-and-score-handover.zip`（約 14MB）をダウンロード
2. またはリポジトリ clone 後に生成:

```bash
bash scripts/create_handover_zip.sh
# → homemedical-quality-and-score-handover.zip がルートに作成される
```

zip を展開したら `DOWNLOAD_README.txt` と `home_visit_demand/docs/HANDOVER.md` を参照。

詳細: [`docs/DOWNLOAD.md`](docs/DOWNLOAD.md)

## リポジトリ

https://github.com/rushwistuq-droid/homemedical-quality-and-score
