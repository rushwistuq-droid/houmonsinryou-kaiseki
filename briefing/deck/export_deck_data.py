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
            "underserved": round(float(r.underserved_ratio), 3),
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
monthly = {}
gpath = CONF / "月次_グループ合計.csv"
if gpath.exists():
    g = pd.read_csv(gpath)
    gr = pd.read_csv(CONF / "月次_院別の伸び.csv", index_col=0)
    fc = pd.read_csv(CONF / "月次_12か月見通し.csv", index_col=0)
    tr = pd.read_csv(CONF / "月次_移管候補.csv")
    monthly = {
        "first_month": str(g.month.iloc[0]), "last_month": str(g.month.iloc[-1]),
        "home_first": int(g.home_patients.iloc[0]), "home_last": int(g.home_patients.iloc[-1]),
        "fac_first": int(g.facility_patients.iloc[0]), "fac_last": int(g.facility_patients.iloc[-1]),
        "fac_peak": int(g.facility_patients.max()), "fac_peak_month": str(g.month.iloc[int(g.facility_patients.idxmax())]),
        "total_first": int(g.total_patients.iloc[0]), "total_last": int(g.total_patients.iloc[-1]),
        "mix_first": round(float(g.home_mix.iloc[0]), 3), "mix_last": round(float(g.home_mix.iloc[-1]), 3),
        "home_12m_ago": int(g.home_patients.iloc[-13]),
        "fac_2025_03": int(g.set_index("month").loc["2025-03", "facility_patients"]), "fac_12m_ago": int(g.facility_patients.iloc[-13]),
        "clinics": {c: {"home_chg_12m": None if pd.isna(r.home_chg_12m) else int(r.home_chg_12m),
                        "home_slope_6m": round(float(r.home_slope_6m), 1) if pd.notna(r.home_slope_6m) else None,
                        "home_trend": r.home_trend, "facility_trend": r.facility_trend,
                        "home_from_peak": int(r.home_from_peak), "facility_from_peak": int(r.facility_from_peak),
                        "home_peak_month": r.home_peak_month, "facility_peak_month": r.facility_peak_month,
                        "fc_low": int(fc.loc[c, "low"]), "fc_high": int(fc.loc[c, "high"])} for c, r in gr.iterrows()},
        "transfers": tr.to_dict(orient="records"),
    }
out = {
    "as_of": "2026-07",
    "model": model,
    "screen": screen.to_dict(orient="records"),
    "clinics": clinics,
    "monthly": monthly,
    "top_sites": top.head(10)[["area", "score", "underserved_ratio", "competition_density", "pred_home_36m_group_net", "reach_target", "nearest_clinic", "nearest_clinic_km"]].round(2).to_dict(orient="records"),
}
(CONF / "deck_data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(CONF / "deck_data.json")
