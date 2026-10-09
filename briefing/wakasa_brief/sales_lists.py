"""院ごとの営業先リスト（CM事業所・訪問看護）。公開データのみ。

各事業所を「最寄りのわかさ院」に割り当て（診療圏の半径以内）、院ごとに距離順で出力する。
多摩クラスターのように圏域が重なる院どうしで、同じ事業所に重複して営業しないための担当表にもなる。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .engine import Engine, haversine_km


def assign_nearest(engine: Engine, df: pd.DataFrame, radius_km: float | None = None) -> pd.DataFrame:
    radius_km = engine.radius_km if radius_km is None else radius_km
    if len(df) == 0:
        return df.assign(clinic=[], distance_km=[])
    d = np.vstack([haversine_km(c.lat, c.lon, df.lat.values, df.lon.values) for c in engine.clinics])
    i = d.argmin(axis=0)
    dmin = d.min(axis=0)
    second = np.sort(d, axis=0)[1] if len(engine.clinics) > 1 else np.full(len(df), np.inf)
    out = df.assign(
        clinic=[engine.clinics[k].name for k in i],
        distance_km=dmin.round(2),
        # 2番目に近い院も半径以内なら「係争」。役割分担の協議対象
        contested=second <= radius_km,
    )
    return out[out.distance_km <= radius_km]


def write_sales_lists(engine: Engine, out_dir: Path) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["clinic", "kind", "distance_km", "contested", "name", "corp", "city", "address", "office_no", "lat", "lon"]
    frames = []
    for kind, df in (("居宅介護支援(CM)", engine.cm_offices), ("訪問看護", engine.nursing)):
        frames.append(assign_nearest(engine, df).assign(kind=kind))
    allf = pd.concat(frames, ignore_index=True)[cols].sort_values(["clinic", "kind", "distance_km"])
    for clinic, g in allf.groupby("clinic"):
        g.to_csv(out_dir / f"{clinic}_営業先.csv", index=False, encoding="utf-8-sig")
    summary = (
        allf.groupby(["clinic", "kind"])
        .agg(件数=("name", "size"), うち係争=("contested", "sum"), 半径3km以内=("distance_km", lambda s: int((s <= 3).sum())))
        .reset_index()
    )
    summary.to_csv(out_dir / "_集計.csv", index=False, encoding="utf-8-sig")
    return summary
