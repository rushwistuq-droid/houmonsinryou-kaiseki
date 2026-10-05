"""院別 月次患者数（機密）から成長曲線を当てはめ、上限と伸び鈍化を判定する。

入力: analysis/confidential/monthly_patients.csv
  列: clinic, month(YYYY-MM), home_patients, facility_patients[, new_home, new_facility, ended_home, ended_facility]
  テンプレ: briefing/templates/monthly_patients.example.csv

S字カーブ（ロジスティック）:  患者数(t) = K / (1 + exp(-k (t - t0)))
  K が「この院の現在のやり方での上限」の推定値。
  データがまだ伸び盛り（変曲点前）だと K は不安定になるため、その場合は「上限未見」とする。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from .engine import ROOT

MONTHLY_PATH = ROOT / "analysis/confidential/monthly_patients.csv"
MIN_POINTS = 12
K_UNSTABLE_MULTIPLE = 3.0  # 推定上限が現在値の3倍超なら「上限未見」
SLOWDOWN_EVIDENCE = 0.7  # 直近6か月の純増が前6か月の7割未満になって初めて「鈍化」とみなす


@dataclass
class CurveFit:
    clinic: str
    series: str
    n_points: int
    current: float
    growth_last6: float  # 直近6か月の純増（人/月）
    growth_prev6: float  # その前6か月の純増（人/月）
    K: float | None
    k: float | None
    t0: float | None
    r2: float | None
    status: str

    @property
    def slowdown(self) -> float | None:
        if self.growth_prev6 and self.growth_prev6 > 0:
            return self.growth_last6 / self.growth_prev6
        return None


def load_monthly(path: Path = MONTHLY_PATH) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["month"] = pd.PeriodIndex(df.month, freq="M")
    df["clinic"] = df.clinic.replace({"リーフシティ市川": "市川", "浦和針ヶ谷": "浦和"})
    return df.sort_values(["clinic", "month"]).reset_index(drop=True)


def _logistic(t, K, k, t0):
    return K / (1.0 + np.exp(-k * (t - t0)))


def fit_curve(t: np.ndarray, y: np.ndarray, clinic: str, series: str) -> CurveFit:
    t, y = np.asarray(t, float), np.asarray(y, float)
    cur = float(y[-1]) if len(y) else 0.0
    g6 = (y[-1] - y[-7]) / 6 if len(y) >= 7 else float("nan")
    g6p = (y[-7] - y[-13]) / 6 if len(y) >= 13 else float("nan")
    base = dict(clinic=clinic, series=series, n_points=len(y), current=cur, growth_last6=g6, growth_prev6=g6p)
    if len(y) < MIN_POINTS or cur <= 0:
        return CurveFit(**base, K=None, k=None, t0=None, r2=None, status="データ不足")
    try:
        p0 = [max(y) * 1.5, 0.1, t[len(t) // 2]]
        (K, k, t0), _ = curve_fit(_logistic, t, y, p0=p0, bounds=([max(y) * 0.9, 1e-3, -240], [max(y) * 20, 2.0, 600]), maxfev=20000)
        yhat = _logistic(t, K, k, t0)
        r2 = 1 - ((y - yhat) ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-9)
    except (RuntimeError, ValueError):
        return CurveFit(**base, K=None, k=None, t0=None, r2=None, status="当てはめ不可")
    flat = abs(g6) < 0.005 * cur and abs(g6p) < 0.005 * cur  # 月0.5%未満の増減＝横ばい
    decel = flat or (g6p > 0 and g6 < SLOWDOWN_EVIDENCE * g6p)
    # 直線的な伸びにもS字は当てはまってしまうため、実データで減速が見えない限り上限とは言わない
    if K > cur * K_UNSTABLE_MULTIPLE or t[-1] < t0 or not decel:
        status = "上限未見（成長継続中）"
    elif cur >= 0.9 * K:
        status = "上限接近"
    else:
        status = "伸び鈍化局面"
    return CurveFit(**base, K=float(K), k=float(k), t0=float(t0), r2=float(r2), status=status)


def analyze_monthly(df: pd.DataFrame, home_start: dict[str, str]) -> pd.DataFrame:
    """院ごと・系列（居宅/施設/合計）ごとの成長曲線診断。home_start は院名→在宅開始月。"""
    rows = []
    for clinic, g in df.groupby("clinic"):
        if clinic not in home_start:
            continue
        start = pd.Period(home_start[clinic], freq="M")
        t = np.array([(m - start).n for m in g.month])
        series = {
            "居宅": g.home_patients.values,
            "施設": g.facility_patients.values,
            "合計": g.home_patients.values + g.facility_patients.values,
        }
        for name, y in series.items():
            f = fit_curve(t, y, clinic, name)
            rows.append({**f.__dict__, "slowdown": f.slowdown})
    return pd.DataFrame(rows)


def ramp_table(df: pd.DataFrame, home_start: dict[str, str]) -> pd.DataFrame:
    """開院後月数 × 院 の居宅患者数（立ち上げカーブ比較用）。"""
    rows = []
    for clinic, g in df.groupby("clinic"):
        if clinic not in home_start:
            continue
        start = pd.Period(home_start[clinic], freq="M")
        for m, h, f in zip(g.month, g.home_patients, g.facility_patients):
            rows.append({"clinic": clinic, "months_open": (m - start).n, "home": h, "facility": f})
    return pd.DataFrame(rows)
