"""院ごとの指数表（公開部分＋機密部分）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .engine import ROOT, Engine

def _latest_month() -> str:
    """月次データがあればその最新月、無ければ単月実績の時点。"""
    path = ROOT / "analysis/confidential/monthly_patients.csv"
    if path.exists():
        return str(pd.read_csv(path, usecols=["month"]).month.max())
    return "2026-07"


AS_OF = _latest_month()
CONF_ACTUALS = ROOT / "home_visit_demand/data/confidential/actuals_2026-07.yaml"
CONF_OPS = ROOT / "analysis/confidential/operational_data.yaml"
CONF_MONTHLY = ROOT / "analysis/confidential/monthly_patients.csv"
NAME_ALIAS = {"リーフシティ市川": "市川", "浦和針ヶ谷": "浦和"}


def months_between(start: str, end: str = AS_OF) -> int:
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, end.split("-"))
    return (y1 - y0) * 12 + (m1 - m0)


def load_actuals(prefer_monthly: bool = True) -> pd.DataFrame | None:
    """機密実績（居宅・施設・医師FTE）。無ければ None。

    月次データ（analysis/confidential/monthly_patients.csv）があれば、その最新月を使う。
    居宅はがん医総を含む（総数−施設）。
    """
    if not CONF_ACTUALS.exists():
        return None
    a = yaml.safe_load(CONF_ACTUALS.read_text(encoding="utf-8"))
    rows = {c["id"]: {"home": c["actual_home_patients"], "facility": c["actual_facility_patients"]} for c in a["clinics"]}
    df = pd.DataFrame.from_dict(rows, orient="index")
    df["as_of"] = a.get("meta", {}).get("as_of", AS_OF)
    if prefer_monthly and CONF_MONTHLY.exists():
        m = pd.read_csv(CONF_MONTHLY)
        latest = m.sort_values("month").groupby("clinic").tail(1).set_index("clinic")
        name_to_id = {NAME_ALIAS.get(c["name"], c["name"]): c["id"] for c in a["clinics"]}
        for name, r in latest.iterrows():
            cid = name_to_id.get(NAME_ALIAS.get(name, name))
            if cid in df.index:
                df.loc[cid, ["home", "facility", "as_of"]] = [int(r.home_patients), int(r.facility_patients), r.month]
        df[["home", "facility"]] = df[["home", "facility"]].astype(int)
    if CONF_OPS.exists():
        ops = yaml.safe_load(CONF_OPS.read_text(encoding="utf-8"))
        fte = {NAME_ALIAS.get(k, k): v for k, v in ops.get("physicians_fte", {}).items()}
        names = {c["id"]: NAME_ALIAS.get(c["name"], c["name"]) for c in a["clinics"]}
        df["fte"] = [fte.get(names[i], np.nan) for i in df.index]
    return df


def build_environment(engine: Engine | None = None) -> pd.DataFrame:
    """公開データのみで作る院別の地域指数。"""
    E = engine or Engine()
    excl = E.exclusive_share()
    rows = []
    for c in E.clinics:
        p = E.point(c.lat, c.lon)
        x = excl[c.id]
        rows.append(
            {
                "id": c.id,
                "name": c.name,
                "pref": c.pref,
                "era": c.era,
                "home_start": c.home_start,
                "months_open": months_between(c.home_start),
                **{k: v for k, v in p.items() if k not in ("lat", "lon", "radius_km", "pref")},
                **x,
                "exclusive_market_home": p["market_home"] * x["exclusive_ratio"],
                "exclusive_latent_home": p["latent_home"] * x["exclusive_ratio"],
            }
        )
    return pd.DataFrame(rows).set_index("id")


def add_performance(env: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """実績と組み合わせた指数（機密扱い）。"""
    df = env.join(actuals, how="left")
    df["total"] = df.home + df.facility
    df["home_mix"] = df.home / df.total
    df["patients_per_fte"] = df.total / df.fte
    df["home_per_fte"] = df.home / df.fte
    df["capture_home"] = df.home / df.market_home
    df["capture_home_exclusive"] = df.home / df.exclusive_market_home
    df["capture_latent"] = df.home / df.latent_home
    df["capture_latent_exclusive"] = df.home / df.exclusive_latent_home
    # 公平シェア: 実効競合＋自院1ユニットで需要を等分した場合の取り分
    df["fair_share_home"] = df.exclusive_market_home / (df.competitor_units * df.exclusive_ratio + 1)
    df["fair_share_ratio"] = df.home / df.fair_share_home
    df["facility_penetration"] = df.facility / df.facility_residents
    df["home_per_month"] = df.home / df.months_open.clip(lower=1)
    # 自院が最寄りのエリアにあるCM事業所1か所あたりの居宅患者（営業の深さ）
    df["home_per_cm"] = df.home / (df.cm_offices_n * df.exclusive_ratio)
    return df
