# 在宅支援施設の精密集計と居宅患者目標計算

地域の **在支診・在支病** を公的データで精密に数え、院ごとの **実務居宅KPI** を算出します。

## 経営指標（v0.5）

| 指標 | 意味 |
|------|------|
| **実務KPI** | 本命。成熟院は実績+年次増分／居宅比シフト。未成熟は公平シェア |
| **公平シェアKPI** | 参照。競合按分の獲得目標 |
| **能力上限** | specialty / FTE |
| **居宅ミックス** | 施設偏重→目標比40%（伸長50%）へのシフトギャップ |

開院初期（例: 浦和）は `new_clinics_ignore_priority` で優先対象外。

### 実効競合

- 機能強化型は **施設単位フラグ**（JMAP type 1/2）
- 従来型 ×0.35、非在支訪問の軽加算
- **自グループ院名は競合から除外**

## CLI

```bash
PYTHONPATH=home_care_target/src:home_visit_demand/src

python3 -m home_care_target.cli
python3 -m home_care_target.cli --clinic ひばりが丘
python3 -m home_care_target.cli --dashboard --write-outputs
python3 -m home_care_target.cli --actions --months 12 --write-outputs
```

紹介経路実績: `analysis/confidential/referral_funnel.yaml`  
（テンプレ: `home_care_target/data/templates/referral_funnel.example.yaml`）

## テスト

```bash
PYTHONPATH=home_care_target/src:home_visit_demand/src \
  python3 -m unittest discover -s home_care_target/tests -v
```
