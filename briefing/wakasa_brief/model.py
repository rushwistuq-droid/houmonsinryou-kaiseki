"""居宅患者の獲得予測モデルと既存院の飽和度診断。

予測モデル（13院の横断データで推定。浦和は開院3か月のため除外）:

    log(居宅患者) = a + b·log(在宅開始後月数) + c·log(未充足度) + d·[施設重視期に開院]

未充足度 = 潜在居宅需要（東京都の受療率）÷ 顕在居宅需要（地元県の受療率）。
東京都内はほぼ1.0、埼玉・千葉は約2倍。

診断は次のレンズで行う:
  1. 年数・地域補正後の実力 = 実績 ÷ モデル期待値
  2. 同条件の上位院との比較（到達率）= 実績 ÷ 到達目安
     到達目安 = 自院が最寄りの潜在居宅需要 × 同じ地域タイプの上位院の取り込み率
     地域タイプ: 未充足度1.2以上＝未充足型、未満＝都市型。上位院＝在宅開始24か月以上の院のうち
     取り込み率の上位2院の平均。本院は先行者（地域で最初に訪問診療を始めた）で他院の目安にならないため除外。
  3. 月次推移（直近6か月の伸び・頭打ち）
医師数は患者数に合わせて増やす運用のため、医師1人あたり患者数は原因ではなく「次の増員の目安」として扱う。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FIRST_MOVER_ID = "honin"  # 地域で最も早く訪問診療を始めた院。目安の計算から除く
MIN_MONTHS_FOR_FIT = 6
PEER_MIN_MONTHS = 24
PEER_TOP_N = 2
UNDERSERVED_TYPE_THRESHOLD = 1.2
NEXT_HIRE_PER_FTE = 250  # 医師1人あたりこれ以上なら次の増員を検討する目安（原因ではない）
NEAR_PEER_TOP = 0.85  # 上位院の水準の85%以上＝自院担当エリアでは上位水準
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


def fit_growth_model(df: pd.DataFrame, exclude_first_mover: bool = True) -> GrowthModel:
    """院別指数表（home, months_open, underserved_ratio, era 列が必要）から推定。

    本院は地域で最初に訪問診療を始めた先行者で、他院の伸び方の参考にならないため既定で除外する
    （含めても係数はほぼ同じであることを確認済み）。
    """
    d = df[df.months_open >= MIN_MONTHS_FOR_FIT].dropna(subset=["home"])
    if exclude_first_mover:
        d = d[d.index != FIRST_MOVER_ID]
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


def area_type(underserved_ratio) -> np.ndarray:
    u = np.asarray(underserved_ratio, dtype=float)
    return np.where(u >= UNDERSERVED_TYPE_THRESHOLD, "未充足型", "都市型")


def peer_benchmarks(df: pd.DataFrame) -> dict[str, dict]:
    """地域タイプ別に「同条件の上位院」の取り込み率（自院が最寄りの潜在居宅需要に対する居宅患者の割合）。"""
    d = df.copy()
    d["share"] = d.home / d.exclusive_latent_home
    d["type"] = area_type(d.underserved_ratio)
    d = d[(d.months_open >= PEER_MIN_MONTHS) & (d.index != FIRST_MOVER_ID)]
    out = {}
    for t, g in d.groupby("type"):
        top = g.sort_values("share", ascending=False).head(PEER_TOP_N)
        out[t] = {"share": float(top.share.mean()), "members": list(top["name"]), "n_peers": int(len(g))}
    return out


def reach_target(exclusive_latent_home, underserved_ratio, bench: dict[str, dict]):
    """同じ地域タイプの上位院並みに自院担当エリアを取り込んだ場合の居宅患者数。"""
    types = area_type(underserved_ratio)
    share = np.array([bench.get(t, {"share": np.nan})["share"] for t in np.atleast_1d(types)], dtype=float)
    pool = np.asarray(exclusive_latent_home, dtype=float)
    if np.ndim(pool) == 0:
        share = share[0]
    return share * pool, share


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
    bench = peer_benchmarks(out)
    out["area_type"] = area_type(out.underserved_ratio)
    out["territory_share"] = out.home / out.exclusive_latent_home
    out["reach_target"], out["reach_share"] = reach_target(out.exclusive_latent_home, out.underserved_ratio, bench)
    out["penetration_of_target"] = out.home / out.reach_target
    out["headroom_home"] = (out.reach_target - out.home).clip(lower=0)
    out["months_to_target"] = [
        model.months_to_reach(t, h, m) for t, h, m in zip(out.reach_target, out.home, out.months_open)
    ]
    out["years_to_target"] = (out.months_to_target - out.months_open) / 12.0
    # 現在の実力のまま3年経った場合の見込み（同じ成長カーブ）
    b = model.coef[1]
    out["home_in_3y"] = out.home * ((out.months_open + 36) / out.months_open.clip(lower=1)) ** b
    res = [_verdict(cid, r) for cid, r in out.iterrows()]
    out["verdict"] = [r[0] for r in res]
    out["cause"] = [r[1] for r in res]
    out["action"] = [r[2] for r in res]
    out["verdict_notes"] = [r[3] for r in res]
    out["hire_note"] = [
        f"医師1人あたり{v:.0f}人（次の増員の目安）" if pd.notna(v) and v >= NEXT_HIRE_PER_FTE else "" for v in out.patients_per_fte
    ]
    return out


def _verdict(cid: str, r: pd.Series) -> tuple[str, str, str, str]:
    """(判定, 主因の候補, 打ち手, 補足) を返す。"""
    notes = []
    if r.home_mix < 0.30:
        notes.append(f"居宅比{r.home_mix:.0%}。施設を抑える方針の下では居宅の伸びが成長の中心")
    if r.months_open < RAMP_MONTHS:
        return "立ち上げ期（判定保留）", "—", "立ち上げ基準カーブで月次追跡", " / ".join(notes + ["開院12か月未満"])
    p, perf = r.penetration_of_target, r.performance_index
    pace = "期待を上回る" if perf >= 1.15 else ("期待を下回る" if perf <= 0.85 else "期待並み")
    trend_up = r.get("home_trend") == "増加"
    if cid == FIRST_MOVER_ID:
        state = "増加中" if trend_up else "横ばい"
        return (
            f"先行者として地域で確立（同条件の上位院の約{p:.1f}倍・{state}）",
            "先行者優位",
            "現状維持＋周辺の未開拓エリアへの展開",
            " / ".join(notes + ["地域で最初に訪問診療を始めた院。他院の目安には使わない"]),
        )
    stalled = r.get("home_curve_status") == "上限接近" or r.get("home_trend") in ("横ばい", "減少")
    overlap = r.exclusive_ratio < 0.5
    if stalled:
        if p >= NEAR_PEER_TOP:
            cause = "担当エリアが狭い（他院と重複）" if overlap else "担当エリア内では上位水準"
            action = "担当エリアの再設定・エリア外（隣接地域）の開拓"
        elif overlap:
            cause = "他院との重複＋エリア内にも取り込み余地"
            action = "担当エリアの整理と、エリア内の紹介経路（CM・病院）の強化"
        elif r.competition_density >= 9:
            cause = "競合過密"
            action = "強みのある紹介元（病院・CM）への集中、差別化"
        else:
            cause = "居宅の獲得の仕組み（紹介経路）"
            action = "紹介経路（CM・病院の退院調整・訪看）の強化"
        trend = "減少" if r.get("home_trend") == "減少" else "横ばい"
        notes.append(f"居宅が直近6か月{trend}。同条件の上位院の{p:.0%}の水準")
        return f"停滞（{pace}）", cause, action, " / ".join(notes)
    if p >= NEAR_PEER_TOP:
        v, cause, action = "上位水準で成長中", "—", "現状の獲得方法を他院へ横展開"
    elif p < 0.4:
        v, cause, action = "伸長余地大", "—", "立ち上げ・成長ペースの維持"
    else:
        v, cause, action = "成長中", "—", "成長ペースの維持"
    return f"{v}（{pace}）", cause, action, " / ".join(notes)


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
    d = df[(df.months_open >= MIN_MONTHS_FOR_FIT) & (df.index != FIRST_MOVER_ID)].copy()
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
