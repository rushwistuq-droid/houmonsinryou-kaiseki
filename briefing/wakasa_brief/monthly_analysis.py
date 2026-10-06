"""院別 月次患者数の詳細解析（機密データ。出力は analysis/confidential/ のみ）。

入力: analysis/confidential/monthly_patients.csv
  clinic, month, home_patients（がん医総を含む居宅＝総数−施設）, facility_patients, home_cancer_patients, total_patients

主な解析:
  1. データ品質（急変月の検出、定義変更）
  2. 院別の伸び（直近3・6・12か月の純増、トレンドの傾きと有意性、ピークからの下落）
  3. 院間の移管の推定（同じ月に一方が減り、他方が増える）
  4. 立ち上げカーブ（開院後月数で揃えた比較）
  5. 成長曲線（S字）による上限推定と伸びの鈍化
  6. 獲得予測モデルの時系列での検証（各月の実績で推定し直しても係数が安定か）
  7. 12か月先の見通し（直近トレンドの延長）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .monthly import fit_curve

SPIKE_SIGMA = 3.0  # 月次増減が院ごとの標準偏差の何倍を超えたら「急変」とするか
SPIKE_MIN_ABS = 15  # 急変とみなす最小の人数


def load(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["month"] = pd.PeriodIndex(df.month, freq="M")
    return df.sort_values(["clinic", "month"]).reset_index(drop=True)


SERIES_COL = {"facility": "facility_patients", "home": "home_patients"}


def load_events(path) -> list[dict]:
    """確認済みの補正イベント（analysis/confidential/monthly_events.yaml）。無ければ空。"""
    import yaml

    from pathlib import Path

    path = Path(path)
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("events", [])


def apply_adjustments(df: pd.DataFrame, events: list[dict], kinds: tuple[str, ...] = ("移管", "集計修正")) -> pd.DataFrame:
    """移管・集計修正による水準の段差を、イベント月より前の値に delta を足して取り除く。

    例: 2025年4月に施設 −121 の移管 → 2025年3月以前の施設を121人少なく扱い、自然増減だけを見る。
    spread: linear のイベント（徐々にずれた報告値の修正）は、ずれが少しずつ積み上がったとみなして按分する。
    グループ合計では移管は内部の付け替えなので kinds=("集計修正",) だけを使う。
    """
    out = df.copy()
    for e in events:
        if e.get("kind") not in kinds:
            continue
        col = SERIES_COL[e["series"]]
        ev = pd.Period(e["month"], freq="M")
        mask = (out.clinic == e["clinic"]) & (out.month < ev)
        if e.get("spread") == "linear":
            # 「少しずつずれていた」報告値の修正: 系列の最初の月は0、修正直前の月で delta 全額になるよう按分
            first = out.loc[out.clinic == e["clinic"], "month"].min()
            span = max((ev - first).n, 1)
            frac = np.array([((m - first).n + 1) / span for m in out.loc[mask, "month"]])
            out.loc[mask, col] = (out.loc[mask, col] + np.round(int(e["delta"]) * np.minimum(frac, 1.0))).clip(lower=0)
        else:
            out.loc[mask, col] = (out.loc[mask, col] + int(e["delta"])).clip(lower=0)
    out["total_patients"] = out.home_patients + out.facility_patients
    if "home_mix" in out:
        out["home_mix"] = out.home_patients / out.total_patients
    return out


def add_months_open(df: pd.DataFrame, home_start: dict[str, str]) -> pd.DataFrame:
    df = df.copy()
    df["months_open"] = [
        (m - pd.Period(home_start[c], freq="M")).n if c in home_start else np.nan for c, m in zip(df.clinic, df.month)
    ]
    df["home_mix"] = df.home_patients / df.total_patients
    return df


# ------------------------------------------------------------------ 1. 品質
def detect_spikes(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c, g in df.groupby("clinic"):
        for col, label in (("facility_patients", "施設"), ("home_patients", "居宅")):
            d = g[col].diff()
            sd = d.iloc[1:].std()
            for m, v, prev, cur in zip(g.month, d, g[col].shift(), g[col]):
                if pd.notna(v) and abs(v) >= max(SPIKE_MIN_ABS, SPIKE_SIGMA * sd) and prev and prev > 0:
                    rows.append({"clinic": c, "month": str(m), "series": label, "change": int(v), "from": int(prev), "to": int(cur)})
    return pd.DataFrame(rows).sort_values(["month", "clinic"]) if rows else pd.DataFrame()


def transfer_candidates(spikes: pd.DataFrame, opening: dict[str, str]) -> pd.DataFrame:
    """同じ月に「減った院」と「増えた院（新規開院を含む）」がある月を移管候補とする。"""
    rows = []
    if spikes.empty:
        return pd.DataFrame()
    for (m, s), g in spikes.groupby(["month", "series"]):
        losers = g[g.change < 0]
        gainers = g[g.change > 0]
        opened = [c for c, st in opening.items() if st == m]
        if len(losers) and (len(gainers) or opened):
            rows.append(
                {
                    "month": m,
                    "series": s,
                    "減少": "・".join(f"{r.clinic}{r.change:+d}" for r in losers.itertuples()),
                    "増加・開院": "・".join([f"{r.clinic}{r.change:+d}" for r in gainers.itertuples()] + [f"{c}（開院）" for c in opened]),
                    "減少合計": int(losers.change.sum()),
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 2. 伸び
def _slope(y: np.ndarray) -> tuple[float, float]:
    """月あたりの傾きと t 値（単回帰）。"""
    y = np.asarray(y, float)
    x = np.arange(len(y), dtype=float)
    if len(y) < 4 or np.all(y == y[0]):
        return 0.0, 0.0
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    se = np.sqrt((resid**2).sum() / (len(y) - 2) / ((x - x.mean()) ** 2).sum())
    return float(b), float(b / se) if se > 0 else float("inf")


def growth_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c, g in df.groupby("clinic"):
        g = g.reset_index(drop=True)
        last = g.iloc[-1]
        row = {"clinic": c, "latest_month": str(last.month), "home": int(last.home_patients), "facility": int(last.facility_patients),
               "total": int(last.total_patients), "home_mix": float(last.home_mix), "months_observed": len(g)}
        for col, key in (("home_patients", "home"), ("facility_patients", "facility"), ("total_patients", "total")):
            y = g[col].values
            for k in (3, 6, 12):
                row[f"{key}_chg_{k}m"] = int(y[-1] - y[-1 - k]) if len(y) > k else np.nan
            b6, t6 = _slope(y[-7:]) if len(y) >= 7 else (np.nan, np.nan)
            b12, t12 = _slope(y[-13:]) if len(y) >= 13 else (np.nan, np.nan)
            row[f"{key}_slope_6m"], row[f"{key}_t_6m"] = b6, t6
            row[f"{key}_slope_12m"], row[f"{key}_t_12m"] = b12, t12
            row[f"{key}_peak"] = int(y.max())
            row[f"{key}_peak_month"] = str(g.month.iloc[int(y.argmax())])
            row[f"{key}_from_peak"] = int(y[-1] - y.max())
        rows.append(row)
    out = pd.DataFrame(rows).set_index("clinic")
    out["home_trend"] = [_trend_label(r.home_slope_6m, r.home_t_6m, r.home) for r in out.itertuples()]
    out["facility_trend"] = [_trend_label(r.facility_slope_6m, r.facility_t_6m, r.facility) for r in out.itertuples()]
    return out


def _trend_label(slope, t, level) -> str:
    if pd.isna(slope):
        return "判定不可"
    rel = slope / max(level, 1)
    if abs(t) < 2 or abs(rel) < 0.003:  # 統計的に有意でない、または月0.3%未満
        return "横ばい"
    return "増加" if slope > 0 else "減少"


# ------------------------------------------------------------------ 4. 立ち上げ
def ramp_points(df: pd.DataFrame, clinics_opened_in_window: list[str], marks=(3, 6, 9, 12, 18, 24)) -> pd.DataFrame:
    rows = []
    for c in clinics_opened_in_window:
        g = df[df.clinic == c].set_index("months_open")
        row = {"clinic": c}
        for m in marks:
            row[f"m{m}"] = int(g.loc[m, "home_patients"]) if m in g.index else np.nan
        row["latest_months_open"] = int(g.index.max())
        row["home_per_month_since_open"] = float(g.home_patients.iloc[-1] / max(g.index.max(), 1))
        rows.append(row)
    return pd.DataFrame(rows).set_index("clinic")


# ------------------------------------------------------------------ 5. S字
def curve_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c, g in df.groupby("clinic"):
        t = g.months_open.values
        for col, label in (("home_patients", "居宅"), ("facility_patients", "施設"), ("total_patients", "合計")):
            f = fit_curve(t, g[col].values, c, label)
            rows.append({**f.__dict__, "slowdown": f.slowdown})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 6. モデルの時系列検証
def model_stability(df: pd.DataFrame, env: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """各月の実績で獲得予測モデルを推定し直し、係数と誤差の安定性を見る。"""
    from .model import fit_growth_model

    rows = []
    name_to_id = {r["name"]: i for i, r in env.iterrows()}
    for m in months:
        snap = df[df.month == pd.Period(m, freq="M")]
        e = env.copy()
        e["home"] = np.nan
        for r in snap.itertuples():
            if r.clinic in name_to_id:
                e.loc[name_to_id[r.clinic], "home"] = r.home_patients
                e.loc[name_to_id[r.clinic], "months_open"] = r.months_open
        e = e.dropna(subset=["home"])
        if (e.months_open >= 6).sum() < 6:
            continue
        mod = fit_growth_model(e)
        rows.append({"month": m, "n": mod.n, "b_months": mod.coef[1], "c_underserved": mod.coef[2], "d_facility_era": mod.coef[3],
                     "r2": mod.r2, "loo_pct": mod.loo_pct})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 7. 見通し
def forecast_12m(df: pd.DataFrame, model=None, env: pd.DataFrame | None = None) -> pd.DataFrame:
    """12か月先の居宅患者の見通し。

    - トレンド延長: 直近12か月（データが短い院は全期間）の線形の傾きをそのまま延長
    - モデル延長: 現在の実績 × (12か月後の月数 / 現在の月数)^b （獲得予測モデルの成長カーブ）
    両者を並べ、低い方〜高い方を幅として示す。
    """
    rows = []
    b = model.coef[1] if model is not None else None
    for c, g in df.groupby("clinic"):
        y = g.home_patients.values
        n = min(13, len(y))
        slope, _ = _slope(y[-n:])
        cur, mo = y[-1], int(g.months_open.iloc[-1])
        trend = max(0.0, cur + slope * 12)
        curve = cur * ((mo + 12) / max(mo, 1)) ** b if b is not None and mo > 0 else np.nan
        rows.append({"clinic": c, "home_now": int(cur), "trend_12m": round(trend), "curve_12m": round(curve) if pd.notna(curve) else np.nan,
                     "low": round(min(trend, curve)) if pd.notna(curve) else round(trend),
                     "high": round(max(trend, curve)) if pd.notna(curve) else round(trend),
                     "slope_per_month": round(slope, 1)})
    return pd.DataFrame(rows).set_index("clinic")


def group_totals(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("month")[["home_patients", "facility_patients", "total_patients"]].sum()
    g["home_mix"] = g.home_patients / g.total_patients
    g["clinics_reporting"] = df[df.total_patients > 0].groupby("month").clinic.nunique()
    return g
