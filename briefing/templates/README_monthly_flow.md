# 月次の新規・終了・紹介元の記録（今後の運用案）

停滞している院の原因が「新規が少ない（紹介不足）」のか「終了が多い（看取り・入院・転院）」のかを分けるための最小限の記録。
院長・マネージャーが月1回、院ごとに1行を記入する（`monthly_flow.example.csv` と同じ列）。

| 列 | 意味 |
|----|------|
| new_home / new_facility | その月の新規患者（居宅／施設） |
| end_home_death / end_home_hospital / end_home_other | 居宅の終了（看取り・死亡／入院／転居・他院・その他） |
| end_facility | 施設の終了 |
| ref_cm / ref_hospital / ref_nursing / ref_family_self / ref_other | 新規居宅の紹介元（ケアマネ／病院の退院調整／訪問看護／本人・家族／その他） |

- 患者個人の情報（氏名・ID）は書かない。院ごとの人数だけ。
- 記入したファイルは機密扱い（`analysis/confidential/monthly_flow.csv` に置く。リポジトリには入れない）。
- 3か月分たまれば、院別の「新規率・終了率・紹介元の偏り」を出せる。
