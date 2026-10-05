"""院ごとの指数表（公開部分＋機密部分）。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .engine import ROOT, Engine

AS_OF = "2026-07"
CONF_ACTUALS = ROOT / "home_visit_demand/data/confidential/actuals_2026-07.yaml"
CONF_OPS = ROOT / "analysis/confidential/operational_data.yaml"
NAME_ALIAS = {"リーフシティ市川": "市川", "浦和針ヶ谷": "浦和"}


def months_between(start: str, end: str = AS_OF) -> int:
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, end.split("-"))
    return (y1 - y0) * 12 + (m1 - m0)


def load_actuals() -> pd.DataFrame | None:
    """機密実績（居宅・施設・医師FTE）。無ければ None。"""
    if not CONF_ACTUALS.exists():
        return None
    a = yaml.safe_load(CONF_ACTUALS.read_text(encoding="utf-8"))
    rows = {c["id"]: {"home": c["actual_home_patients"], "facility": c["actual_facility_patients"]} for c in a["clinics"]}
    df = pd.DataFrame.from_dict(rows, orient="index")
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
    return df
