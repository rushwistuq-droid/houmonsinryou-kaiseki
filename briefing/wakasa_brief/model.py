"""居宅患者の獲得予測モデルと既存院の飽和度診断。

予測モデル（13院の横断データで推定。浦和は開院3か月のため除外）:

    log(居宅患者) = a + b·log(在宅開始後月数) + c·log(未充足度) + d·[施設重視期に開院]

未充足度 = 潜在居宅需要（東京都の受療率）÷ 顕在居宅需要（地元県の受療率）。
東京都内はほぼ1.0、埼玉・千葉は約2倍。

飽和度診断は3つのレンズで行う:
  1. 年数・地域補正後の実力 = 実績 ÷ モデル期待値
  2. 到達目安に対する浸透度 = 実績 ÷ 到達目安
     到達目安 = 自院が最寄りの潜在居宅需要 × 本院の浸透率 × (本院の競合密度 ÷ 自院の競合密度)
  3. 医師キャパシティ = 患者数 ÷ 医師FTE
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BENCHMARK_ID = "honin"
MIN_MONTHS_FOR_FIT = 6
CAPACITY_TIGHT_PER_FTE = 250  # 本院・所沢・三軒茶屋の水準。これ以上は医師増員が先
RAMP_MONTHS = 12  # これ未満は立ち上げ期として判定保留


@dataclass
class GrowthModel:
    coef: np.ndarray  # [a, b_months, c_underserved, d_facility_era]
    r2: float
    loo_rmse_log: float
    n: int
    underserved_range: tuple[float, float]
    residuals: dict[str, float] = field(default_factory=dict)

    @property
    def loo_pct(self) -> float:
        return float(np.exp(self.loo_rmse_log) - 1)

    def predict(self, months, underserved, facility_era=False):
        lo, hi = self.underserved_range
        u = np.clip(np.asarray(underserved, dtype=float), lo, hi)
        m = np.maximum(np.asarray(months, dtype=float), 1.0)
        a, b, c, d = self.coef
        return np.exp(a + b * np.log(m) + c * np.log(u) + d * np.asarray(facility_era, dtype=float))

    def months_to_reach(self, target, current, months_now):
        """現在の実績から同じ成長カーブ（月数^b）で target に達する月数。"""
        b = self.coef[1]
        if current <= 0 or target <= current:
            return float(months_now)
        return float(months_now * (target / current) ** (1.0 / b))


def _design(df: pd.DataFrame) -> np.ndarray:
    return np.column_stack(
        [
            np.ones(len(df)),
            np.log(df.months_open.clip(lower=1).values),
            np.log(df.underserved_ratio.values),
            (df.era == "施設重視期").astype(float).values,
        ]
    )


def fit_growth_model(df: pd.DataFrame) -> GrowthModel:
    """院別指数表（home, months_open, underserved_ratio, era 列が必要）から推定。"""
    d = df[df.months_open >= MIN_MONTHS_FOR_FIT].dropna(subset=["home"])
    d = d[d.home > 0]
    X, y = _design(d), np.log(d.home.values)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ coef
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    errs = []
    for i in range(len(d)):
        mask = np.arange(len(d)) != i
        c_i, *_ = np.linalg.lstsq(X[mask], y[mask], rcond=None)
        errs.append(y[i] - X[i] @ c_i)
    errs = np.array(errs)
    return GrowthModel(
        coef=coef,
        r2=float(r2),
        loo_rmse_log=float(np.sqrt((errs**2).mean())),
        n=len(d),
        underserved_range=(float(d.underserved_ratio.min()), float(d.underserved_ratio.max())),
        residuals=dict(zip(d.index, np.exp(errs))),  # 実績÷(その院を除いて推定した期待値)
    )


def benchmark_share(df: pd.DataFrame) -> tuple[float, float]:
    """(本院の浸透率, 本院の競合密度)。"""
    b = df.loc[BENCHMARK_ID]
    return float(b.home / b.exclusive_latent_home), float(b.competition_density)


def reach_target(exclusive_latent_home, competition_density, bench_pen, bench_cd):
    """本院並みの浸透を、競合の厚さで割り引いた到達目安（居宅患者数）。"""
    cd = np.asarray(competition_density, dtype=float)
    with np.errstate(divide="ignore"):
        share = bench_pen * (bench_cd / cd)
    share = np.minimum(share, bench_pen * 1.5)  # 競合が極端に薄い（ゼロ含む）地点で過大にならないよう上限
    return share * np.asarray(exclusive_latent_home, dtype=float), share


def diagnose(df: pd.DataFrame, model: GrowthModel, monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    """既存院の飽和度診断。df は機密の実績列を含む院別指数表。

    monthly を渡すと（院名で引ける: home_curve_status, home_slope_6m, home_trend, facility_trend）、
    月次推移の「頭打ち」を4つ目のレンズとして判定に加える。
    """
    out = df.copy()
    if monthly is not None:
        mm = monthly.reindex(out["name"].values)
        for col in ("home_curve_status", "home_slope_6m", "home_trend", "facility_trend", "facility_from_peak"):
            out[col] = mm[col].values if col in mm else np.nan
    out["expected_home"] = model.predict(out.months_open, out.underserved_ratio, out.era == "施設重視期")
    out["performance_index"] = out.home / out.expected_home
    out["performance_index_loo"] = pd.Series(model.residuals)
    bench_pen, bench_cd = benchmark_share(out)
    out["reach_target"], out["reach_share"] = reach_target(
        out.exclusive_latent_home, out.competition_density, bench_pen, bench_cd
    )
    out["penetration_of_target"] = out.home / out.reach_target
    out["headroom_home"] = (out.reach_target - out.home).clip(lower=0)
    out["months_to_target"] = [
        model.months_to_reach(t, h, m) for t, h, m in zip(out.reach_target, out.home, out.months_open)
    ]
    out["years_to_target"] = (out.months_to_target - out.months_open) / 12.0
    # 現在の実力のまま3年経った場合の見込み（同じ成長カーブ）
    b = model.coef[1]
    out["home_in_3y"] = out.home * ((out.months_open + 36) / out.months_open.clip(lower=1)) ** b
    verdicts, notes = [], []
    for cid, r in out.iterrows():
        v, n = _verdict(cid, r)
        verdicts.append(v)
        notes.append(n)
    out["verdict"] = verdicts
    out["verdict_notes"] = notes
    return out


def _verdict(cid: str, r: pd.Series) -> tuple[str, str]:
    notes = []
    if r.patients_per_fte >= CAPACITY_TIGHT_PER_FTE:
        notes.append(f"医師1人あたり{r.patients_per_fte:.0f}人＝キャパ逼迫。増患より先に医師増員")
    if r.home_mix < 0.30:
        notes.append(f"居宅比{r.home_mix:.0%}＝施設偏重。施設→居宅の構成転換余地")
    if r.months_open < RAMP_MONTHS:
        return "立ち上げ期（判定保留）", " / ".join(notes + ["開院12か月未満。立ち上げ基準で追跡"])
    if cid == BENCHMARK_ID:
        if r.get("home_trend") == "増加":
            return "ベンチマーク院（月次で増加中＝上限未到達）", " / ".join(
                notes + ["到達目安の基準そのもの。月次では居宅が増え続けており、上限にはまだ達していない"]
            )
        return "ベンチマーク院（月次推移で判定）", " / ".join(
            notes + ["到達目安の基準そのもの。上限判定は月次推移の伸び鈍化で行う"]
        )
    p, perf = r.penetration_of_target, r.performance_index
    # モデル誤差が±21%のため、±15%を超える差のみ「上回る／下回る」とする
    pace = "期待を上回る" if perf >= 1.15 else ("期待を下回る" if perf <= 0.85 else "期待並み")
    stalled = r.get("home_curve_status") == "上限接近" or r.get("home_trend") in ("横ばい", "減少")
    if stalled:
        # 月次で居宅が頭打ち。地域の到達目安に届いていないなら、原因は市場以外
        if r.patients_per_fte >= CAPACITY_TIGHT_PER_FTE:
            cause = "医師キャパ"
        elif r.exclusive_ratio < 0.5:
            cause = "グループ内重複・営業エリア"
        else:
            cause = "営業・紹介経路"
        trend = "減少" if r.get("home_trend") == "減少" else "横ばい"
        notes.append(f"居宅が直近6か月{trend}（到達目安の{p:.0%}で停滞）→ 主因の候補: {cause}")
        return f"停滞・{cause}（{pace}）", " / ".join(notes)
    if p >= 0.8:
        v = "上限接近"
        notes.append("周辺エリアの深掘りより、隣接エリア出店・構成転換・医師増員を検討")
    elif p < 0.4:
        v = "伸長余地大"
    else:
        v = "成長中"
    return f"{v}（{pace}）", " / ".join(notes)


# 候補指数の比較（どの指数が居宅患者数を説明するか）。結果は集計値のみで個別院の実績は含まない。
SCREEN_CANDIDATES = {
    "月数のみ": [],
    "月数＋高齢者数(75歳以上)": ["elderly_75"],
    "月数＋顕在居宅需要": ["market_home"],
    "月数＋潜在居宅需要": ["latent_home"],
    "月数＋実効競合ユニット": ["competitor_units"],
    "月数＋競合密度": ["competition_density"],
    "月数＋競合あたり居宅需要": ["market_per_competitor"],
    "月数＋入居系施設の入居者数": ["facility_residents"],
    "月数＋排他率(グループ重複の少なさ)": ["exclusive_ratio"],
    "月数＋CM事業所密度": ["cm_per_10k75"],
    "月数＋訪問看護密度": ["nursing_per_10k75"],
    "月数＋未充足度": ["underserved_ratio"],
    "月数＋未充足度＋競合密度": ["underserved_ratio", "competition_density"],
    "月数＋未充足度＋排他率": ["underserved_ratio", "exclusive_ratio"],
    "月数＋未充足度＋開院時期【採用】": ["underserved_ratio", "facility_era"],
    "月数＋未充足度＋開院時期＋CM事業所密度": ["underserved_ratio", "facility_era", "cm_per_10k75"],
    "月数＋未充足度＋開院時期＋訪問看護密度": ["underserved_ratio", "facility_era", "nursing_per_10k75"],
}


def screen_indices(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df.months_open >= MIN_MONTHS_FOR_FIT].copy()
    d["facility_era"] = (d.era == "施設重視期").astype(float)
    y = np.log(d.home.values)
    rows = []
    for label, vs in SCREEN_CANDIDATES.items():
        cols = [np.ones(len(d)), np.log(d.months_open.values)] + [
            d[v].values if v == "facility_era" else np.log(d[v].values) for v in vs
        ]
        X = np.column_stack(cols)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        r2 = 1 - ((y - X @ coef) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        errs = []
        for i in range(len(d)):
            m = np.arange(len(d)) != i
            c, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            errs.append(y[i] - X[i] @ c)
        loo = float(np.exp(np.sqrt(np.mean(np.square(errs)))) - 1)
        rows.append(
            {
                "モデル": label,
                "R2": round(float(r2), 2),
                "予測誤差(LOO)": round(loo, 2),
                "追加指数の係数": ", ".join(f"{v}={c:+.2f}" for v, c in zip(vs, coef[2:])),
            }
        )
    return pd.DataFrame(rows)
