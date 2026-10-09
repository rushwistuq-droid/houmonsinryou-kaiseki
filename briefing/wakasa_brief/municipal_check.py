"""市区町村単位の訪問診療患者数の推計（自治体の実数との照合用）。

院の診療圏（円）ではなく市区町村の人口で、エンジンと同じ受療率・算式を当てる。
  - 年齢: 市区町村別 5歳階級（2020国勢調査・2025推計）。中間年は線形補間
  - 95歳以上: 市区町村表は90歳以上までのため、近傍メッシュの 95歳以上÷85歳以上 の比で分ける
  - 受療率: NDB（2022年度）の都道府県別・年齢別の月あたり患者数。年による受療率の変化は入れていない
  - 入居系施設の入居者: 介護施設の所在市区町村で集計
"""

from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from .engine import HVD, Engine, haversine_km

K65 = ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
K75 = K65[2:]
K85 = K65[4:]


def _muni(code: str) -> dict:
    with gzip.open(HVD / "data/processed/municipalities_age5.json.gz", "rt", encoding="utf-8") as f:
        return next(m for m in json.load(f) if m["code"] == code)


def estimate(engine: Engine, code: str, years=(2020, 2021, 2022, 2023, 2024, 2025)) -> pd.DataFrame:
    m = _muni(code)
    ms = engine.mesh
    near = ms[haversine_km(m["lat"], m["lon"], ms.lat.values, ms.lon.values) <= 4]
    r95 = float(near.elderly_95.sum() / near.elderly_85.sum()) if near.elderly_85.sum() else 0.08
    fac = engine.facilities[(engine.facilities.pref == m["pref"]) & (engine.facilities.city == m["name"])]
    residents = float(fac.residents_est.sum())
    g20, g25 = engine.pref_growth[m["pref_code"]]
    growth = max(0.9, min(1.25, g25 / g20))  # _demand が掛ける2020→2025補正を打ち消すため
    rows = []
    for y in years:
        t = (y - 2020) / 5
        a = {k: (1 - t) * m["ages_2020"][k] + t * m["ages"][k] for k in K65}
        e65, e75, e85 = sum(a[k] for k in K65), sum(a[k] for k in K75), sum(a[k] for k in K85)
        e = np.array([e65, e75, e85, r95 * e85])
        dem = engine._demand({m["pref_code"]: e}, residents)
        bands = np.array([e65 - e75, e75 - e85, e85 * (1 - r95), e85 * r95])
        total, home_raw, fac_raw = bands @ engine._rate(m["pref_code"])
        rows.append({
            "code": code, "name": m["name"], "year": y, "elderly_65": e65, "elderly_75": e75,
            "est_home": dem["home"] / growth, "est_facility": dem["facility"] / growth,
            "est_total": total, "est_home_ndb_only": home_raw,
        })
    return pd.DataFrame(rows)


def compare(engine: Engine, checks: list[dict]) -> pd.DataFrame:
    out = []
    for c in checks:
        years = sorted(int(y) for y in c["counts"])
        est = estimate(engine, str(c["code"]), years)
        est["actual"] = [c["counts"][y] for y in years]
        est["ratio_home"] = est.actual / est.est_home
        est["ratio_total"] = est.actual / est.est_total
        out.append(est)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
