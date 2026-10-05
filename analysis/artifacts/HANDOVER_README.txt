わかさクリニックグループ 在宅・居宅患者分析 引き継ぎZIP
================================================

作成日: 2026-08-17
元リポジトリ: github.com/rushwistuq-droid/---
元ブランチ: cursor/home-care-target-patients-1cfb

【最初に読む】
  analysis/新リポジトリ_初回指示.md  … 新エージェントへの指示文（コピペ用）
  analysis/引き継ぎ資料.md           … 全体統合サマリ

【機密データ】
  analysis/confidential/wakasa_patient_actuals.yaml  … 13院実績（2026-07）
  ※ 公開リポジトリでは必ず gitignore すること

【本流コード】
  home_care_target/  … 供給・KPI・実績突合
  home_visit_demand/ … 需要推計

【他ブランチ取り込み分（未統合）】
  analysis/imported_from_branches/regional-analysis-853a/
  analysis/imported_from_branches/home-visit-estimation-28cb/

【動作確認】
  export PYTHONPATH=home_care_target/src:home_visit_demand/src
  python3 -m home_care_target.cli --dashboard
