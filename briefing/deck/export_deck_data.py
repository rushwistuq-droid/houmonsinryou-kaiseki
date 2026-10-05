#!/usr/bin/env python3
"""スライド用の数値を JSON に書き出す（機密。出力は analysis/confidential/briefing/ のみ）。"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "analysis/confidential/briefing"
PUB = ROOT / "briefing/output"

diag = pd.read_csv(CONF / "clinic_diagnosis.csv", index_col=0)
screen = pd.read_csv(PUB / "index_screening.csv").fillna("")
top = pd.read_csv(PUB / "site_top30.csv")
model = json.loads((PUB / "growth_model.json").read_text(encoding="utf-8"))

clinics = []
for cid, r in diag.iterrows():
    clinics.append(
        {
            "id": cid,
            "name": r["name"],
            "pref": r.pref,
            "era": r.era,
            "months": int(r.months_open),
            "home": int(r.home),
            "facility": int(r.facility),
            "fte": float(r.fte),
            "home_mix": round(float(r.home_mix), 3),
            "per_fte": round(float(r.patients_per_fte), 1),
            "perf": round(float(r.performance_index), 2),
            "expected": round(float(r.expected_home), 0),
            "reach_target": round(float(r.reach_target), 0),
            "penetration": round(float(r.penetration_of_target), 3),
            "home_in_3y": round(float(r.home_in_3y), 0),
            "underserved": round(float(r.underserved_ratio), 2),
            "competition_density": round(float(r.competition_density), 2),
            "exclusive_ratio": round(float(r.exclusive_ratio), 2),
            "home_per_cm": round(float(r.home_per_cm), 2),
            "cm_n": int(r.cm_offices_n),
            "e85_growth_25_35": round(float(r.e85_growth_25_35), 2),
            "verdict": r.verdict,
            "notes": r.verdict_notes if isinstance(r.verdict_notes, str) else "",
        }
    )
sales = pd.read_csv(PUB / "sales_lists/_集計.csv")
cm = sales[sales.kind.str.startswith("居宅介護支援")].set_index("clinic")
for c in clinics:
    if c["name"] in cm.index:
        c["cm_assigned"] = int(cm.loc[c["name"], "件数"])
        c["cm_contested_share"] = round(float(cm.loc[c["name"], "うち係争"] / cm.loc[c["name"], "件数"]), 2)
out = {
    "as_of": "2026-07",
    "model": model,
    "screen": screen.to_dict(orient="records"),
    "clinics": clinics,
    "top_sites": top.head(10)[["area", "score", "underserved_ratio", "competition_density", "pred_home_36m_group_net", "reach_target", "nearest_clinic", "nearest_clinic_km"]].round(2).to_dict(orient="records"),
}
(CONF / "deck_data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(CONF / "deck_data.json")
