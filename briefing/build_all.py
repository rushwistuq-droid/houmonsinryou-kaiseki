#!/usr/bin/env python3
"""理事長面談資料の全数値・図表を再生成する。

    python3 briefing/build_all.py            # 全部（格子スコアは約40秒）
    python3 briefing/build_all.py --no-grid  # 出店格子を前回結果から再利用

出力:
  briefing/output/                      公開データのみ（Git管理）
  analysis/confidential/briefing/       実績を含むもの（Git管理外）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing.wakasa_brief import charts  # noqa: E402
from briefing.wakasa_brief.clinics_table import add_performance, build_environment, load_actuals  # noqa: E402
from briefing.wakasa_brief.engine import Engine  # noqa: E402
from briefing.wakasa_brief.model import diagnose, fit_growth_model, peer_benchmarks, screen_indices  # noqa: E402
from briefing.wakasa_brief import monthly_analysis as ma  # noqa: E402
from briefing.wakasa_brief import monthly_flow as mf  # noqa: E402
from briefing.wakasa_brief.clinics_table import CONF_MONTHLY  # noqa: E402


def ma_monthly_path():
    return CONF_MONTHLY
from briefing.wakasa_brief.sales_lists import write_sales_lists  # noqa: E402
from briefing.wakasa_brief.site_score import SiteScorer, add_scores, top_sites  # noqa: E402

PUB = ROOT / "briefing/output"
CONF = ROOT / "analysis/confidential/briefing"

# 公開表に出す列（実績を含まない地域指数）
ENV_COLS = [
    "name", "pref", "era", "home_start", "months_open",
    "elderly_65", "elderly_75", "market_home", "latent_home", "underserved_ratio",
    "market_facility", "facility_count", "facility_residents",
    "competitors_n", "competitors_enhanced_n", "competitor_units", "competition_density",
    "exclusive_ratio", "exclusive_market_home", "exclusive_latent_home",
    "siblings_in_radius", "siblings_16km", "e75_growth_20_25",
    "cm_offices_n", "cm_per_10k75", "nursing_n", "nursing_per_10k75",
    "e75_growth_25_35", "e85_growth_25_35", "e85_growth_25_40", "latent_home_2035",
]
SITE_COLS = [
    "area", "lat", "lon", "score", "pred_home_36m", "pred_home_36m_group_net", "reach_target",
    "elderly_65", "elderly_75", "market_home", "latent_home", "underserved_ratio",
    "competitor_units", "competition_density", "facility_residents", "exclusive_ratio_new",
    "e75_growth_20_25", "e85_growth_25_35", "e85_growth_25_40", "cm_offices_n", "cm_per_10k75",
    "nursing_n", "nursing_per_10k75", "latent_home_2035",
    "nearest_clinic", "nearest_clinic_km", "underserved_extrapolated",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-grid", action="store_true", help="出店格子を前回の CSV から再利用")
    args = ap.parse_args()
    PUB.mkdir(parents=True, exist_ok=True)

    E = Engine()
    env = build_environment(E)
    env[ENV_COLS].round(4).to_csv(PUB / "clinic_environment.csv", encoding="utf-8-sig")
    print(f"院別 地域指数: {PUB / 'clinic_environment.csv'}")
    if len(E.cm_offices):
        sales = write_sales_lists(E, PUB / "sales_lists")
        print(f"院別 営業先リスト（CM・訪看）: {PUB / 'sales_lists'}")
        print(sales.pivot(index="clinic", columns="kind", values="件数").to_string())

    # 自治体の実数との照合（あれば）
    chk_path = ROOT / "analysis/confidential/municipal_checks.yaml"
    if chk_path.exists():
        import yaml

        from briefing.wakasa_brief.municipal_check import compare

        CONF.mkdir(parents=True, exist_ok=True)
        chk = compare(E, yaml.safe_load(chk_path.read_text(encoding="utf-8"))["checks"])
        chk.round(3).to_csv(CONF / "検証_市区町村の実数.csv", index=False, encoding="utf-8-sig")
        print("自治体の実数との照合:")
        print(chk[["name", "year", "actual", "est_home", "ratio_home", "est_total", "ratio_total"]].round(2).to_string(index=False))

    actuals = load_actuals()
    if actuals is None:
        print("機密実績が無いため、モデル推定・院別診断・出店予測はスキップします。")
        return
    CONF.mkdir(parents=True, exist_ok=True)
    df = add_performance(env, actuals)
    model = fit_growth_model(df)
    bench = peer_benchmarks(df)
    CONF.mkdir(parents=True, exist_ok=True)
    (CONF / "peer_benchmarks.json").write_text(json.dumps(bench, ensure_ascii=False, indent=1), encoding="utf-8")

    # 月次推移（あれば）: 院別の伸び・頭打ち判定を診断の4つ目のレンズに使う
    mdf = gtab = ctab = ramps = None
    if ma_monthly_path().exists():
        starts = {c.name: c.home_start for c in E.clinics}
        mdf_raw = ma.add_months_open(ma.load(ma_monthly_path()), starts)
        events = ma.load_events(ma_monthly_path().parent / "monthly_events.yaml")
        # 分析は補正後（移管・集計修正の段差を除いた実態ベース）。グループ合計は集計修正のみ補正
        mdf = ma.apply_adjustments(mdf_raw, events)
        mdf_group = ma.apply_adjustments(mdf_raw, events, kinds=("集計修正",))
        if events:
            print(f"補正イベント {len(events)}件を適用（analysis/confidential/monthly_events.yaml）")
        gtab = ma.growth_table(mdf)
        ctab = ma.curve_table(mdf)
        gtab["home_curve_status"] = ctab[ctab.series == "居宅"].set_index("clinic").status
        ramps = mdf.rename(columns={"home_patients": "home"})[["clinic", "months_open", "home"]]
    diag = diagnose(df, model, gtab)

    # 新規・終了（あれば）: 横ばいの原因を A 取り切り／B 新規不足／C 終了過多に分ける
    flow_sheets: dict[str, pd.DataFrame] = {}
    fcls = None
    flow_path = ma_monthly_path().parent / "monthly_flow.csv"
    if mdf is not None and flow_path.exists():
        flow = mf.adjust_flow(mf.load(flow_path), events)
        stock = mdf[["clinic", "month", "home_patients", "facility_patients"]]
        fcls = mf.classify(mf.flow_table(flow, stock), diag)
        f6 = mf.flow_table(flow, stock, window=6)
        fcls["eq_home_6m"] = f6.eq_home
        fcls["eq_ratio_home_6m"] = f6.eq_ratio_home
        fcls["new_home_6m"] = f6.new_home_m
        gflow = mf.group_flow(flow)
        flow_sheets = {
            "新規終了_院別": fcls,
            "新規終了_グループ": gflow,
            "新規終了_突合（院別）": mf.reconcile_summary(flow, stock),
            "新規終了_突合（食い違い月）": mf.reconcile(flow, stock),
            "新規終了_データ（補正後）": flow.assign(month=flow.month.astype(str)),
        }
        refs = {k: round(float(v), 4) for k, v in fcls.attrs.items()}
        (CONF / "flow_refs.json").write_text(json.dumps(refs, ensure_ascii=False), encoding="utf-8")
        keep = ["new_home_m", "end_rate_home", "stay_home_months", "eq_home", "eq_ratio_home", "inflow_per_target",
                "inflow_vs_ref", "end_rate_vs_ref", "new_home_needed", "new_home_chg_yoy", "flow_outlook", "stall_cause", "flow_note"]
        diag = diag.join(fcls[keep], on="name")
        print(f"新規・終了: 物差し {refs}")
        print(fcls[["home", "new_home_m", "end_rate_home", "eq_home", "inflow_vs_ref", "end_rate_vs_ref", "flow_outlook", "stall_cause"]].round(2).to_string())

    model_info = {
        "radius_km": E.radius_km,
        "formula": "log(居宅患者) = a + b·log(在宅開始後月数) + c·log(未充足度) + d·[施設重視期]",
        "coef": dict(zip(["a", "b_months", "c_underserved", "d_facility_era"], model.coef.round(4).tolist())),
        "r2": round(model.r2, 3),
        "loo_error_pct": round(100 * model.loo_pct, 1),
        "n": model.n,
        "underserved_range": [round(x, 3) for x in model.underserved_range],
        # 地域タイプ別の上位院の取り込み率。公開ファイルのため丸める（個別院の患者数を逆算できないように）
        "peer_benchmark_share": {t: round(v["share"], 2) for t, v in bench.items()},
        "peer_benchmark_rule": "在宅開始24か月以上・本院を除く院のうち、取り込み率の上位2院の平均。未充足度1.2以上＝未充足型",
    }
    # モデル係数は実績を集約したものだが個別院の数値は復元できないため公開側にも置く
    (PUB / "growth_model.json").write_text(json.dumps(model_info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"獲得予測モデル: R2={model.r2:.2f}  LOO誤差±{100 * model.loo_pct:.0f}%")

    diag.round(4).to_csv(CONF / "clinic_diagnosis.csv", encoding="utf-8-sig")
    screen = screen_indices(df)
    screen.to_csv(PUB / "index_screening.csv", index=False, encoding="utf-8-sig")
    print(screen.to_string(index=False))

    # 出店候補
    grid_csv = PUB / "site_scores_grid.csv"
    if args.no_grid and grid_csv.exists():
        grid = pd.read_csv(grid_csv)
    else:
        scorer = SiteScorer(E, model, bench)
        grid = scorer.score_grid(2.0)
        grid[SITE_COLS].round(4).to_csv(grid_csv, index=False, encoding="utf-8-sig")
    top = top_sites(grid, 30)
    top[SITE_COLS].round(3).to_csv(PUB / "site_top30.csv", index=False, encoding="utf-8-sig")
    print(f"出店候補 上位30: {PUB / 'site_top30.csv'}")

    # 月次の詳細（機密）
    monthly_sheets: dict[str, pd.DataFrame] = {}
    if mdf is not None:
        opening = {c.name: c.home_start for c in E.clinics}
        spikes = ma.detect_spikes(mdf)  # 補正後に残る急変＝未確認の変化
        new_clinics = [c.name for c in E.clinics if c.home_start >= str(mdf.month.min())]
        monthly_sheets = {
            "月次_院別の伸び": gtab,
            "月次_成長曲線": ctab,
            "月次_急変（補正前）": ma.detect_spikes(mdf_raw),
            "月次_急変（補正後）": spikes,
            "月次_移管候補": ma.transfer_candidates(ma.detect_spikes(mdf_raw), opening),
            "月次_立ち上げ": ma.ramp_points(mdf, new_clinics),
            "月次_モデル安定性": ma.model_stability(
                mdf, env, [str(p) for p in pd.period_range("2024-06", str(mdf.month.max()), freq="3M")]
            ),
            "月次_12か月見通し": ma.forecast_12m(mdf, model),
            "月次_グループ合計": ma.group_totals(mdf_group),
            "月次_グループ合計（補正前）": ma.group_totals(mdf_raw),
            "月次_補正イベント": pd.DataFrame(events),
        }
        for name, t in {**monthly_sheets, **{f"月次_{k}": v for k, v in flow_sheets.items()}}.items():
            t.to_csv(CONF / f"{name}.csv", encoding="utf-8-sig")
        print(f"月次解析: {CONF}/月次_*.csv")
        print(gtab[["home", "home_chg_12m", "home_slope_6m", "home_trend", "facility_trend", "home_curve_status"]].round(1).to_string())
    else:
        print("月次データ未投入（analysis/confidential/monthly_patients.csv）。成長曲線の判定は保留。")

    # Excel（理事長・事務局がそのまま開ける形）
    with pd.ExcelWriter(CONF / "wakasa_briefing_data.xlsx") as xw:
        diag.round(4).to_excel(xw, sheet_name="院別_診断")
        env[ENV_COLS].round(4).to_excel(xw, sheet_name="院別_地域指数")
        top[SITE_COLS].round(3).to_excel(xw, sheet_name="出店候補_上位30", index=False)
        pd.DataFrame([model_info]).T.to_excel(xw, sheet_name="予測モデル")
        screen.to_excel(xw, sheet_name="指数の比較", index=False)
        for name, t in monthly_sheets.items():
            t.to_excel(xw, sheet_name=name[:31])
        for name, t in flow_sheets.items():
            t.to_excel(xw, sheet_name=name[:31], index=not name.endswith("（補正後）"))
        if mdf is not None:
            mdf_raw.assign(month=mdf_raw.month.astype(str)).to_excel(xw, sheet_name="月次_データ（整形済み）", index=False)
            mdf.assign(month=mdf.month.astype(str)).to_excel(xw, sheet_name="月次_データ（補正後）", index=False)
    print(f"Excel: {CONF / 'wakasa_briefing_data.xlsx'}")

    # 図表
    figs = CONF / "figures"
    figs.mkdir(exist_ok=True)
    charts.map_underserved(grid, E.clinics, PUB / "fig_map_underserved.png")
    charts.map_site_score(grid, top.head(10), E.clinics, PUB / "fig_map_site_score.png")
    charts.model_fit(diag, model, figs / "fig_model_fit.png")
    charts.peer_position(diag, figs / "fig_saturation.png")
    charts.growth_curves(diag, model, figs / "fig_growth_curves.png", ramps=ramps)
    # スライド貼り付け用（タイトルなし）
    slide = figs / "slide"
    slide.mkdir(exist_ok=True)
    charts.SHOW_TITLES = False
    charts.map_underserved(grid, E.clinics, slide / "fig_map_underserved.png")
    charts.map_site_score(grid, top.head(10), E.clinics, slide / "fig_map_site_score.png")
    charts.model_fit(diag, model, slide / "fig_model_fit.png")
    charts.peer_position(diag, slide / "fig_saturation.png")
    charts.growth_curves(diag, model, slide / "fig_growth_curves.png", ramps=ramps)
    charts.SHOW_TITLES = True
    if mdf is not None:
        order = [c.name for c in E.clinics]
        launch = [c for c in ("津田沼", "西日暮里", "高円寺", "市川", "浦和") if c in set(mdf.clinic)]
        us = dict(zip(env["name"], env.underserved_ratio))
        for flag, d in ((True, figs), (False, slide)):
            charts.SHOW_TITLES = flag
            charts.group_trend(monthly_sheets["月次_グループ合計"], d / "fig_m_group_trend.png")
            charts.clinic_small_multiples(mdf, order, d / "fig_m_clinics.png")
            charts.launch_curves(mdf, launch, us, model, d / "fig_m_launch.png")
            charts.forecast_bars(monthly_sheets["月次_12か月見通し"], order, d / "fig_m_forecast.png")
            if fcls is not None:
                charts.group_flow(flow_sheets["新規終了_グループ"], d / "fig_m_group_flow.png")
                charts.flow_balance(fcls, order, d / "fig_m_flow_balance.png")
        charts.SHOW_TITLES = True
    print(f"図表: {PUB}/fig_*.png, {figs}/fig_*.png, {slide}/fig_*.png")


if __name__ == "__main__":
    main()
