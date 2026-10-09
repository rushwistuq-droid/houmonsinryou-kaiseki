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
            "cause": r.cause if isinstance(r.cause, str) else "",
            "action": r.action if isinstance(r.action, str) else "",
            "area_type": r.area_type,
            "territory_share": round(float(r.territory_share), 4),
            "hire_note": r.hire_note if isinstance(r.hire_note, str) else "",
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
flow = {}
fpath = CONF / "月次_新規終了_院別.csv"
if fpath.exists():
    fc = pd.read_csv(fpath, index_col=0)
    gf = pd.read_csv(CONF / "月次_新規終了_グループ.csv")
    fd = pd.read_csv(CONF / "月次_新規終了_データ（補正後）.csv")
    gt = pd.read_csv(CONF / "月次_グループ合計.csv")
    refs = json.loads((CONF / "flow_refs.json").read_text(encoding="utf-8"))
    last12 = gf.tail(12)
    g_home_now = int(monthly["home_last"]) if monthly else None
    # 2024年までに開院した院と、2025年以降に開院した院に分けた居宅新規（月平均）
    first = fd.groupby("clinic").month.min()
    existing = set(first[first <= "2024-12"].index)
    fd["grp"] = ["既存院" if c in existing else "新しい院" for c in fd.clinic]
    fd["year"] = fd.month.str[:4]
    by_year = fd.pivot_table(index="year", columns="grp", values="new_home", aggfunc="sum") / fd.groupby("year").month.nunique().values[:, None]
    end_rate_group = float(last12.end_home.sum() / gt[gt.month.isin(last12.month)].home_patients.sum())
    flow = {
        "window": f"{last12.month.iloc[0]}〜{last12.month.iloc[-1]}",
        "group_new_home_m": round(float(last12.new_home.mean()), 1),
        "group_end_home_m": round(float(last12.end_home.mean()), 1),
        "group_new_fac_m": round(float(last12.new_facility.mean()), 1),
        "group_end_fac_m": round(float(last12.end_facility.mean()), 1),
        "group_new_fac_2024_m": round(float(gf[gf.month.str.startswith("2024")].new_facility.mean()), 1),
        "group_end_rate_home": round(end_rate_group, 4) if end_rate_group else None,
        "group_eq_home": round(float(last12.new_home.mean()) / end_rate_group) if end_rate_group else None,
        "existing_clinics": sorted(existing),
        "new_home_by_year": {y: {k: round(float(v), 1) for k, v in r.dropna().items()} for y, r in by_year.iterrows()},
        "ref_inflow": refs["ref_inflow"], "ref_end_rate": refs["ref_end_rate"],
        "clinics": {c: {k: (None if pd.isna(r[k]) else (round(float(r[k]), 3) if isinstance(r[k], (int, float)) else r[k]))
                        for k in ["home", "new_home_m", "new_home_6m", "new_home_prev12_m", "new_home_chg_yoy", "end_home_m", "end_rate_home",
                                  "stay_home_months", "eq_home", "eq_ratio_home", "eq_home_6m", "inflow_per_target", "inflow_vs_ref",
                                  "end_rate_vs_ref", "new_home_needed", "reach_target", "penetration_of_target", "new_facility_m",
                                  "new_facility_prev12_m", "end_facility_m", "eq_facility", "eq_ratio_facility", "facility",
                                  "flow_outlook", "stall_cause", "flow_note"]}
                    for c, r in fc.iterrows()},
    }
muni = []
mpath = CONF / "検証_市区町村の実数.csv"
if mpath.exists():
    muni = pd.read_csv(mpath).round(3).to_dict(orient="records")
cands = []
cpath = CONF / "出店候補_個別評価.csv"
if cpath.exists():
    cands = pd.read_csv(cpath).round(4).fillna("").to_dict(orient="records")
# 立ち上げ方針の検証: 在宅開始から同じ月数の居宅患者数
era_launch = {}
mp = ROOT / "analysis/confidential/monthly_patients.csv"
if mp.exists():
    import yaml

    st = pd.read_csv(mp)
    starts = {c["name"]: c for c in yaml.safe_load((ROOT / "briefing/data/clinics.yaml").read_text(encoding="utf-8"))["clinics"]}
    st["m"] = [(pd.Period(mo, "M") - pd.Period(starts[c]["home_start"], "M")).n for c, mo in zip(st.clinic, st.month)]
    for c, g in st.groupby("clinic"):
        g = g.set_index("m")
        era_launch[c] = {"era": starts[c]["era"], **{f"h{k}": (int(g.home_patients[k]) if k in g.index else None) for k in (6, 12, 24, 36)},
                         **{f"f{k}": (int(g.facility_patients[k]) if k in g.index else None) for k in (12, 24)}}
peer = json.loads((CONF / "peer_benchmarks.json").read_text(encoding="utf-8"))
out = {
    "as_of": "2026-07",
    "model": model,
    "screen": screen.to_dict(orient="records"),
    "clinics": clinics,
    "monthly": monthly,
    "flow": flow,
    "muni_check": muni,
    "candidates": cands,
    "era_launch": era_launch,
    "peer": peer,
    "top_sites": top.head(10)[["area", "score", "underserved_ratio", "competition_density", "pred_home_36m_group_net", "reach_target", "nearest_clinic", "nearest_clinic_km"]].round(2).to_dict(orient="records"),
}
(CONF / "deck_data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(CONF / "deck_data.json")
