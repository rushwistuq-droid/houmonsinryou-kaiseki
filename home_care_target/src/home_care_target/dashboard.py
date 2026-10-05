"""経営ダッシュボード: 実務KPI（増分）/ 公平シェア / 能力 / 居宅ミックス。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .actuals_compare import load_actuals
from .pipeline import ClinicAnalysis, analyze_all_wakasa


def build_dashboard(
    analyses: Optional[List[ClinicAnalysis]] = None,
    *,
    actuals_path: Optional[Path] = None,
    include_actuals: bool = True,
) -> Dict[str, Any]:
    actuals = {}
    if include_actuals:
        try:
            actuals = load_actuals(actuals_path)
        except FileNotFoundError:
            actuals = {}
    analyses = analyses or analyze_all_wakasa(actuals=actuals)

    rows = []
    for a in analyses:
        row = a.management_row()
        act = actuals.get(a.clinic)
        g = a.growth
        if act:
            home = int(act["home"])
            op = a.operational_kpi_home or 1
            row["actual_home"] = home
            row["actual_facility"] = int(act["facility"])
            row["attainment_vs_operational_kpi"] = round(home / op, 3)
            row["gap_vs_operational_kpi"] = home - op
            row["attainment_vs_fair_share"] = round(home / max(a.kpi_target_home, 1), 3)
            if g and g.ignore_for_priority:
                row["status"] = "開院初期（優先対象外）"
            elif g and g.home_mix and g.home_mix.band == "施設偏重" and g.home_mix.shift_gap_to_target > 0:
                row["status"] = "居宅シフト要"
            elif home >= (g.operational_stretch_home if g else a.acquisition.acquisition_stretch_home):
                row["status"] = "伸長以上"
            elif home >= op:
                row["status"] = "実務KPI達成"
            else:
                row["status"] = "実務KPI未達"
        else:
            row["status"] = "実績未登録"
        rows.append(row)

    meta = {
        "columns": {
            "operational_kpi_home": "本命短期＝成熟院は実績+増分／居宅シフト、未成熟は公平シェア",
            "fair_share_kpi_home": "参照＝競合按分の獲得KPI",
            "capacity_cap_home": "能力上限",
            "home_mix_band": "施設偏重 / 標準 / 居宅寄り",
            "attainment_vs_operational_kpi": "実績居宅 ÷ 実務KPI",
        },
        "policy": "浦和など開院初期は ignore_for_priority。成熟院は増分・居宅ミックスを追う",
    }
    return {"meta": meta, "n_clinics": len(rows), "rows": rows}


def public_dashboard(dash: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for r in dash["rows"]:
        pub = {
            "clinic": r["clinic"],
            "alias": r["alias"],
            "operational_kpi_home": r["operational_kpi_home"],
            "operational_stretch_home": r["operational_stretch_home"],
            "fair_share_kpi_home": r["fair_share_kpi_home"],
            "growth_mode": r["growth_mode"],
            "capacity_cap_home": r["capacity_cap_home"],
            "home_mix_band": r.get("home_mix_band"),
            "home_mix_share": r.get("home_mix_share"),
            "home_shift_gap": r.get("home_shift_gap"),
            "competition_label": r["competition_label"],
            "status": r.get("status"),
            "ignore_for_priority": r.get("ignore_for_priority"),
        }
        if "attainment_vs_operational_kpi" in r:
            pub["attainment_vs_operational_kpi"] = r["attainment_vs_operational_kpi"]
            pub["gap_vs_operational_sign"] = (
                "over"
                if r["gap_vs_operational_kpi"] > 0
                else "at"
                if r["gap_vs_operational_kpi"] == 0
                else "under"
            )
        rows.append(pub)
    return {"meta": dash["meta"], "n_clinics": len(rows), "rows": rows}


def write_dashboard(
    path: Path,
    *,
    public_path: Optional[Path] = None,
) -> Dict[str, Any]:
    dash = build_dashboard()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dash, ensure_ascii=False, indent=2), encoding="utf-8")
    if public_path:
        public_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.write_text(
            json.dumps(public_dashboard(dash), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return dash
