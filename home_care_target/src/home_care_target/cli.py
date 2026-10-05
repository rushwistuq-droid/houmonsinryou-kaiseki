"""CLI: 院ID/座標 → 需要＋実務KPI、ダッシュボード、アクション。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from home_care_target.actions import build_action_plans, public_action_summary, write_action_plans
from home_care_target.actuals_compare import (
    compare_actuals_to_kpi,
    load_actuals,
    rows_to_public_summary,
)
from home_care_target.dashboard import build_dashboard, public_dashboard, write_dashboard
from home_care_target.pipeline import analyze_all_wakasa, analyze_clinic, resolve_clinic


def _print_analysis(a, as_json: bool) -> None:
    if as_json:
        print(json.dumps(a.to_dict(), ensure_ascii=False, indent=2))
        return
    g = a.growth
    print("=" * 72)
    print(f"{a.clinic}（{a.alias}） r={a.radius_km}km FTE={a.physician_fte}")
    print("-" * 72)
    print(f"  需要居宅（重複補正）: {a.demand_home_adjusted:.0f}")
    print(
        f"  競合 在支診/病: {a.competitors_clinics:.0f} / {a.competitors_hospitals:.0f} "
        f"（自グループ除外 {a.excluded_own_group}）"
    )
    print(f"  機能強化型/従来型: {a.clinic_enhanced_est:.0f} / {a.clinic_standard_est:.0f}")
    print(f"  競合: {a.acquisition.competition_label}")
    print()
    print("  【経営指標】")
    print(f"    実務KPI（本命）: {a.operational_kpi_home}  mode={g.mode if g else '-'}")
    print(f"    公平シェアKPI:   {a.kpi_target_home}")
    print(f"    能力上限:        {a.capacity_cap_home:.0f}")
    if g and g.home_mix:
        m = g.home_mix
        print(
            f"    居宅ミックス:    {m.actual_home_share:.0%}（{m.band}） "
            f"目標比{m.target_home_share:.0%} ギャップ{m.shift_gap_to_target}"
        )
    for n in (g.notes if g else [])[:3]:
        print(f"  - {n}")


def run_demo(as_json: bool = False, prefer_points: bool = True) -> int:
    try:
        actuals = load_actuals()
    except FileNotFoundError:
        actuals = {}
    rows = []
    for a in analyze_all_wakasa(prefer_points=prefer_points, actuals=actuals):
        g = a.growth
        rows.append(
            {
                "clinic": a.clinic,
                "competitors_clinics": a.competitors_clinics,
                "competitors_hospitals": a.competitors_hospitals,
                "clinic_enhanced": a.clinic_enhanced_est,
                "clinic_standard": a.clinic_standard_est,
                "excluded_own_group": a.excluded_own_group,
                "effective_supply_units": a.acquisition.effective_supply_units,
                "demand_home_adjusted": a.demand_home_adjusted,
                "fair_share_kpi": a.kpi_target_home,
                "operational_kpi": a.operational_kpi_home,
                "operational_stretch": g.operational_stretch_home if g else None,
                "growth_mode": g.mode if g else None,
                "home_mix_band": g.home_mix.band if g and g.home_mix else None,
                "home_mix_share": g.home_mix.actual_home_share if g and g.home_mix else None,
                "capacity_cap_home": a.capacity_cap_home,
                "competition_label": a.acquisition.competition_label,
            }
        )
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print("=" * 110)
    print("実務KPI（成熟院=増分/居宅シフト）＋公平シェア参照")
    print("=" * 110)
    print(
        f"{'院名':<12} {'診':>4} {'強':>3} {'実務KPI':>7} {'公平':>5} "
        f"{'居宅比':>6} {'帯':<8} {'競合':<8}"
    )
    for r in rows:
        short = r["clinic"].replace("わかさクリニック", "")
        share = f"{r['home_mix_share']:.0%}" if r["home_mix_share"] is not None else "-"
        band = r["home_mix_band"] or "-"
        print(
            f"{short:<12} {r['competitors_clinics']:>4.0f} {r['clinic_enhanced']:>3.0f} "
            f"{r['operational_kpi']:>7} {r['fair_share_kpi']:>5} "
            f"{share:>6} {band:<8} {r['competition_label']:<8}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="居宅患者目標・実務KPI")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--municipal-only", action="store_true")
    parser.add_argument("--clinic", help="院ID/短称（例: ひばりが丘）")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--name", help="新規地点名")
    parser.add_argument("--radius-km", type=float, default=8.0)
    parser.add_argument("--fte", type=float)
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--actions", action="store_true")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--compare-actuals", action="store_true")
    parser.add_argument("--write-outputs", action="store_true")
    args = parser.parse_args(argv)
    prefer_points = not args.municipal_only

    if args.clinic or (args.lat is not None and args.lon is not None):
        point = resolve_clinic(
            args.clinic, lat=args.lat, lon=args.lon, name=args.name, radius_km=args.radius_km
        )
        try:
            actuals = load_actuals()
        except FileNotFoundError:
            actuals = {}
        act = actuals.get(point.name)
        analysis = analyze_clinic(
            point,
            prefer_points=prefer_points,
            physician_fte=args.fte,
            actual_home=act["home"] if act else None,
            actual_facility=act["facility"] if act else None,
        )
        _print_analysis(analysis, args.json)
        return 0

    if args.dashboard:
        dash = build_dashboard()
        if args.json:
            print(json.dumps(dash, ensure_ascii=False, indent=2))
        else:
            print("経営ダッシュボード（実務KPI / 公平シェア / 能力 / 居宅ミックス）")
            print(
                f"{'院':<10} {'実務':>5} {'公平':>5} {'達成':>6} {'帯':<8} {'状態':<14}"
            )
            for r in dash["rows"]:
                att = r.get("attainment_vs_operational_kpi")
                att_s = f"{att:.0%}" if att is not None else "-"
                print(
                    f"{r['alias']:<10} {r['operational_kpi_home']:>5} "
                    f"{r['fair_share_kpi_home']:>5} {att_s:>6} "
                    f"{(r.get('home_mix_band') or '-'):<8} {r.get('status','-'):<14}"
                )
        if args.write_outputs:
            write_dashboard(
                Path("analysis/confidential/management_dashboard.json"),
                public_path=Path(
                    "home_care_target/data/processed/management_dashboard_public.json"
                ),
            )
        return 0

    if args.actions:
        plans = build_action_plans(months=args.months)
        if args.json:
            print(json.dumps(public_action_summary(plans), ensure_ascii=False, indent=2))
        else:
            print(f"院別アクション（{args.months}ヶ月）※開院初期は末尾")
            for p in plans:
                flag = " [対象外]" if p.ignore_for_priority else ""
                print(f"\n#{p.priority} {p.alias}{flag} [{p.status}]")
                print(
                    f"  実務KPI {p.operational_kpi} / 公平 {p.fair_share_kpi} / "
                    f"居宅帯 {p.home_mix_band} シフト差 {p.home_shift_gap}"
                )
                print(f"  月次新規 {p.monthly_new_to_operational} / 紹介={p.referral_source}")
                for act in p.actions:
                    print(f"  - {act}")
        if args.write_outputs:
            write_action_plans(
                Path("analysis/confidential/clinic_action_plans.json"),
                Path("home_care_target/data/processed/clinic_action_plans_public.json"),
                months=args.months,
            )
        return 0

    if args.compare_actuals:
        try:
            rows = compare_actuals_to_kpi()
        except FileNotFoundError as e:
            print(f"実績ファイルなし: {e}")
            return 1
        pub = rows_to_public_summary(rows)
        if args.json:
            print(json.dumps(pub, ensure_ascii=False, indent=2))
        else:
            print("実績 vs 実務KPI / 公平シェア")
            for c in pub["clinics"]:
                short = c["clinic"].replace("わかさクリニック", "")
                print(
                    f"  {short:<12} op={c['operational_kpi']:>4} fair={c['fair_share_kpi']:>3} "
                    f"band={c.get('home_mix_band')} status={c['status']}"
                )
        return 0

    return run_demo(as_json=args.json, prefer_points=prefer_points)


if __name__ == "__main__":
    raise SystemExit(main())
