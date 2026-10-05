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
from briefing.wakasa_brief.model import benchmark_share, diagnose, fit_growth_model, screen_indices  # noqa: E402
from briefing.wakasa_brief.monthly import analyze_monthly, load_monthly, ramp_table  # noqa: E402
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
    "siblings_8km", "siblings_16km", "e75_growth_20_25",
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

    actuals = load_actuals()
    if actuals is None:
        print("機密実績が無いため、モデル推定・院別診断・出店予測はスキップします。")
        return
    CONF.mkdir(parents=True, exist_ok=True)
    df = add_performance(env, actuals)
    model = fit_growth_model(df)
    diag = diagnose(df, model)
    bench_pen, bench_cd = benchmark_share(df)

    model_info = {
        "formula": "log(居宅患者) = a + b·log(在宅開始後月数) + c·log(未充足度) + d·[施設重視期]",
        "coef": dict(zip(["a", "b_months", "c_underserved", "d_facility_era"], model.coef.round(4).tolist())),
        "r2": round(model.r2, 3),
        "loo_error_pct": round(100 * model.loo_pct, 1),
        "n": model.n,
        "underserved_range": [round(x, 3) for x in model.underserved_range],
        # 公開ファイルのため丸める（本院の患者数を逆算できないように）
        "benchmark_penetration": round(bench_pen, 2),
        "benchmark_competition_density": round(bench_cd, 1),
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
        scorer = SiteScorer(E, model, bench_pen, bench_cd)
        grid = scorer.score_grid(2.0)
        grid[SITE_COLS].round(4).to_csv(grid_csv, index=False, encoding="utf-8-sig")
    top = top_sites(grid, 30)
    top[SITE_COLS].round(3).to_csv(PUB / "site_top30.csv", index=False, encoding="utf-8-sig")
    print(f"出店候補 上位30: {PUB / 'site_top30.csv'}")

    # 月次（あれば）
    monthly = load_monthly()
    curves = ramps = None
    if monthly is not None:
        starts = {c.name: c.home_start for c in E.clinics}
        curves = analyze_monthly(monthly, starts)
        ramps = ramp_table(monthly, starts)
        curves.to_csv(CONF / "monthly_curves.csv", index=False, encoding="utf-8-sig")
        print(f"月次成長曲線: {CONF / 'monthly_curves.csv'}")
    else:
        print("月次データ未投入（analysis/confidential/monthly_patients.csv）。成長曲線の判定は保留。")

    # Excel（理事長・事務局がそのまま開ける形）
    with pd.ExcelWriter(CONF / "wakasa_briefing_data.xlsx") as xw:
        diag.round(4).to_excel(xw, sheet_name="院別_診断")
        env[ENV_COLS].round(4).to_excel(xw, sheet_name="院別_地域指数")
        top[SITE_COLS].round(3).to_excel(xw, sheet_name="出店候補_上位30", index=False)
        pd.DataFrame([model_info]).T.to_excel(xw, sheet_name="予測モデル")
        screen.to_excel(xw, sheet_name="指数の比較", index=False)
        if curves is not None:
            curves.to_excel(xw, sheet_name="月次_成長曲線", index=False)
    print(f"Excel: {CONF / 'wakasa_briefing_data.xlsx'}")

    # 図表
    figs = CONF / "figures"
    figs.mkdir(exist_ok=True)
    charts.map_underserved(grid, E.clinics, PUB / "fig_map_underserved.png")
    charts.map_site_score(grid, top.head(10), E.clinics, PUB / "fig_map_site_score.png")
    charts.model_fit(diag, model, figs / "fig_model_fit.png")
    charts.saturation_bars(diag, figs / "fig_saturation.png")
    charts.growth_curves(diag, model, figs / "fig_growth_curves.png", ramps=ramps)
    # スライド貼り付け用（タイトルなし）
    slide = figs / "slide"
    slide.mkdir(exist_ok=True)
    charts.SHOW_TITLES = False
    charts.map_underserved(grid, E.clinics, slide / "fig_map_underserved.png")
    charts.map_site_score(grid, top.head(10), E.clinics, slide / "fig_map_site_score.png")
    charts.model_fit(diag, model, slide / "fig_model_fit.png")
    charts.saturation_bars(diag, slide / "fig_saturation.png")
    charts.growth_curves(diag, model, slide / "fig_growth_curves.png", ramps=ramps)
    charts.SHOW_TITLES = True
    print(f"図表: {PUB}/fig_*.png, {figs}/fig_*.png, {slide}/fig_*.png")


if __name__ == "__main__":
    main()
