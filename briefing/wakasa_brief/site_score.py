"""出店候補地の評価（1都3県の格子点、または任意の住所・座標）。

候補地ごとに2つの数字を出す:
  ① 3年後の居宅患者予測 … 獲得予測モデル（転換期型の立ち上げを仮定）
  ② 到達目安 … 同じ地域タイプ（都市型／未充足型）の上位院の取り込み率 × 「新院が最寄りになる」潜在居宅需要
さらに、既存院との重複を除いた「グループ純増」も出す。

総合スコア(0-100) = ①グループ純増 40% ＋ ②到達目安 40% ＋ ③85歳以上の伸び（2025→2035）20% の順位（パーセンタイル）の加重平均。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Engine, haversine_km
from .model import GrowthModel, reach_target

TARGET_PREFS = ("11", "12", "13", "14")
MIN_ELDERLY_65_PER_KM2 = 150  # 診療圏の65歳以上の密度（人/km²）がこれ未満の地点は対象外（旧: 8km圏で3万人）
HORIZON_MONTHS = 36


def grid_points(engine: Engine, step_km: float = 2.0) -> pd.DataFrame:
    """1都3県の人が住むメッシュを覆う格子点。"""
    m = engine.mesh[engine.mesh.pref.isin(TARGET_PREFS)]
    m = m[m.lon > 138.9]  # 島しょ部を除外
    dlat, dlon = step_km / 110.95, step_km / 90.4
    gl = np.round(m.lat.values / dlat).astype(int)
    go = np.round(m.lon.values / dlon).astype(int)
    pop = m.elderly_65.values
    g = pd.DataFrame({"gl": gl, "go": go, "e": pop}).groupby(["gl", "go"]).e.sum().reset_index()
    g = g[g.e >= 200]  # 格子内に65歳以上が200人以上いる地点のみ
    return pd.DataFrame({"lat": g.gl * dlat, "lon": g.go * dlon}).reset_index(drop=True)


class SiteScorer:
    def __init__(self, engine: Engine, model: GrowthModel, bench: dict[str, dict]):
        self.E, self.model = engine, model
        self.bench = bench
        ma = engine._mesh_arr
        # 各メッシュから最寄り既存院までの距離（重複判定用）
        d = np.vstack([haversine_km(c.lat, c.lon, ma["lat"], ma["lon"]) for c in engine.clinics])
        self._d_exist = d.min(axis=0)

    def exclusive_ratio(self, lat: float, lon: float, radius_km: float | None = None) -> float:
        """新院の診療圏の高齢者のうち、新院が既存院より近い（＝新たに担当する）割合。"""
        radius_km = self.E.radius_km if radius_km is None else radius_km
        ma = self.E._mesh_arr
        d = haversine_km(lat, lon, ma["lat"], ma["lon"])
        inside = d <= radius_km
        tot = ma["e"][inside, 0].sum()
        own = ma["e"][inside & (d < self._d_exist), 0].sum()
        return float(own / tot) if tot else float("nan")

    def evaluate(self, lat: float, lon: float, radius_km: float | None = None) -> dict:
        radius_km = self.E.radius_km if radius_km is None else radius_km
        p = self.E.point(lat, lon, radius_km)
        if not p:
            return {}
        x = self.exclusive_ratio(lat, lon, radius_km)
        pred = float(self.model.predict(HORIZON_MONTHS, p["underserved_ratio"], False))
        target, share = reach_target(p["latent_home"] * x, p["underserved_ratio"], self.bench)
        nearest = min(
            ((c.name, float(haversine_km(lat, lon, c.lat, c.lon))) for c in self.E.clinics), key=lambda t: t[1]
        )
        return {
            **p,
            "exclusive_ratio_new": x,
            "pred_home_36m": pred,
            "pred_home_36m_group_net": pred * x,
            "reach_target": float(target),
            "reach_share": float(share),
            "underserved_extrapolated": p["underserved_ratio"] > self.model.underserved_range[1] * 1.05,
            "nearest_clinic": nearest[0],
            "nearest_clinic_km": nearest[1],
        }

    def score_grid(self, step_km: float = 2.0) -> pd.DataFrame:
        pts = grid_points(self.E, step_km)
        rows = [r for r in (self.evaluate(a, b) for a, b in zip(pts.lat, pts.lon)) if r]
        df = pd.DataFrame(rows)
        df = df[df.pref.isin(TARGET_PREFS) & (df.elderly_65 >= MIN_ELDERLY_65_PER_KM2 * np.pi * self.E.radius_km ** 2)].reset_index(drop=True)
        return add_scores(df, self.E)


def add_scores(df: pd.DataFrame, engine: Engine) -> pd.DataFrame:
    df = df.copy()
    # 3年後の純増 40% + 到達目安 40% + 10年後の需要の伸び（85歳以上 2025→2035）20%
    growth = df.e85_growth_25_35.rank(pct=True) if "e85_growth_25_35" in df else 0.5
    # 人数は整数に丸めてから順位を付ける。未充足度が実績範囲を超える地点は予測が上限値でそろう（同点）ため、
    # 小数点以下の差で順位が大きく動かないようにする（同点は平均順位）
    df["score"] = 100 * (
        0.4 * df.pred_home_36m_group_net.round(0).rank(pct=True) + 0.4 * df.reach_target.round(0).rank(pct=True) + 0.2 * growth
    )
    mu = engine.munis
    names = []
    for la, lo in zip(df.lat, df.lon):
        d = haversine_km(la, lo, mu.lat.values, mu.lon.values)
        i = int(np.argmin(d))
        names.append(f"{mu.pref.iloc[i]}{mu.name.iloc[i]}")
    df["area"] = names
    return df


def top_sites(df: pd.DataFrame, n: int = 20, min_sep_km: float = 6.0, exclude_near_existing_km: float = 4.0) -> pd.DataFrame:
    """スコア上位から、互いに min_sep_km 以上離れた地点を選ぶ（既存院の近くは除外）。"""
    picked: list[int] = []
    for i in df.sort_values("score", ascending=False).index:
        r = df.loc[i]
        if r.nearest_clinic_km < exclude_near_existing_km:
            continue
        if all(haversine_km(r.lat, r.lon, df.loc[j].lat, df.loc[j].lon) >= min_sep_km for j in picked):
            picked.append(i)
        if len(picked) >= n:
            break
    out = df.loc[picked].reset_index(drop=True)
    # 同じ市区町村名が続く場合は、最初の地点からの方角を付けて区別する
    first: dict[str, tuple[float, float]] = {}
    labels = []
    for r in out.itertuples():
        if r.area in first:
            la, lo = first[r.area]
            dy, dx = r.lat - la, (r.lon - lo) * np.cos(np.radians(la))
            d = "北" if dy > abs(dx) else "南" if -dy > abs(dx) else "東" if dx > 0 else "西"
            labels.append(f"{r.area}付近（{d}側）")
        else:
            first[r.area] = (r.lat, r.lon)
            labels.append(f"{r.area}付近")
    out["area"] = labels
    return out
