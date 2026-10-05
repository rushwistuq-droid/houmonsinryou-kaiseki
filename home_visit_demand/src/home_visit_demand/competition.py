"""外部競合密度（厚生局・在宅療養支援診療所 + 補助指標）。"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .estimator import haversine_km
from .precision import DATA_DIR

OWN_NAME_RE = ("わかさ", "Wakasa", "WAKASA")


@lru_cache(maxsize=1)
def _load_zaishishin() -> pd.DataFrame:
    path = DATA_DIR / "zaishishin.csv.gz"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["kind"] == "在宅療養支援診療所"].copy()
    return df


@lru_cache(maxsize=1)
def _load_home_name_competitors() -> pd.DataFrame:
    path = DATA_DIR / "competitors_home.csv.gz"
    if not path.exists():
        return pd.DataFrame(columns=["ID", "name", "lat", "lon"])
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def _load_all_clinics() -> pd.DataFrame:
    path = DATA_DIR / "clinics_all_coords.csv.gz"
    if not path.exists():
        return pd.DataFrame(columns=["ID", "lat", "lon"])
    return pd.read_csv(path)


def load_zaishishin_meta() -> dict:
    path = DATA_DIR / "zaishishin_meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_competitors_meta() -> dict:
    path = DATA_DIR / "competitors_meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _count_in_radius(df: pd.DataFrame, lat: float, lon: float, radius_km: float) -> int:
    if df.empty:
        return 0
    ddeg = (radius_km + 1.0) / 80.0
    sub = df[
        (df["lat"] >= lat - ddeg)
        & (df["lat"] <= lat + ddeg)
        & (df["lon"] >= lon - ddeg)
        & (df["lon"] <= lon + ddeg)
    ]
    if sub.empty:
        return 0
    n = 0
    for r in sub.itertuples(index=False):
        if haversine_km(lat, lon, float(r.lat), float(r.lon)) <= radius_km:
            n += 1
    return n


def _zaishi_in_radius(lat: float, lon: float, radius_km: float) -> tuple[int, list[dict]]:
    df = _load_zaishishin()
    if df.empty:
        return 0, []
    ddeg = (radius_km + 1.0) / 80.0
    sub = df[
        (df["lat"] >= lat - ddeg)
        & (df["lat"] <= lat + ddeg)
        & (df["lon"] >= lon - ddeg)
        & (df["lon"] <= lon + ddeg)
    ]
    hits: list[dict] = []
    for r in sub.itertuples(index=False):
        name = str(getattr(r, "name", "") or "")
        if any(x in name for x in OWN_NAME_RE):
            continue
        d = haversine_km(lat, lon, float(r.lat), float(r.lon))
        if d <= radius_km:
            hits.append(
                {
                    "name": name,
                    "distance_km": round(d, 2),
                    "address": getattr(r, "address", ""),
                    "zaishi_class": getattr(r, "zaishi_class", ""),
                }
            )
    hits.sort(key=lambda x: x["distance_km"])
    return len(hits), hits[:15]


def _named_home_excluding_own(lat: float, lon: float, radius_km: float) -> int:
    df = _load_home_name_competitors()
    if df.empty:
        return 0
    ddeg = (radius_km + 1.0) / 80.0
    sub = df[
        (df["lat"] >= lat - ddeg)
        & (df["lat"] <= lat + ddeg)
        & (df["lon"] >= lon - ddeg)
        & (df["lon"] <= lon + ddeg)
    ]
    n = 0
    for r in sub.itertuples(index=False):
        name = str(getattr(r, "name", "") or "")
        if any(x in name for x in OWN_NAME_RE):
            continue
        if haversine_km(lat, lon, float(r.lat), float(r.lon)) <= radius_km:
            n += 1
    return n


def competition_metrics(lat: float, lon: float, radius_km: float, elderly_65: float) -> dict:
    """圏内の外部競合指標（在支診を主指標）。"""
    zaishi_n, top = _zaishi_in_radius(lat, lon, radius_km)
    named_n = _named_home_excluding_own(lat, lon, radius_km)
    all_n = _count_in_radius(_load_all_clinics(), lat, lon, radius_km)
    per_10k_zaishi = 10000.0 * zaishi_n / elderly_65 if elderly_65 else 0.0
    per_10k_all = 10000.0 * all_n / elderly_65 if elderly_65 else 0.0

    # 在支診件数ベースのティア（8km想定）
    if zaishi_n >= 150 or per_10k_zaishi >= 4.0:
        tier = "外部競合・高"
    elif zaishi_n >= 70 or per_10k_zaishi >= 2.0:
        tier = "外部競合・中"
    elif zaishi_n >= 30 or per_10k_zaishi >= 1.0:
        tier = "外部競合・低〜中"
    else:
        tier = "外部競合・低"

    return {
        "zaishishin_competitors": zaishi_n,
        "home_visit_competitors": zaishi_n,  # 後方互換（主指標を在支診に）
        "named_home_competitors": named_n,
        "all_clinics_in_radius": all_n,
        "zaishishin_per_10k_elderly": round(per_10k_zaishi, 2),
        "home_competitors_per_10k_elderly": round(per_10k_zaishi, 2),
        "clinics_per_10k_elderly": round(per_10k_all, 2),
        "external_competition_tier": tier,
        "top_home_competitors": top,
        "meta": {
            "zaishishin": load_zaishishin_meta(),
            "name_approx": load_competitors_meta(),
        },
    }


def adjust_share_for_external_competition(
    low: float, high: float, metrics: dict
) -> tuple[float, float, list[str]]:
    notes: list[str] = []
    tier = metrics.get("external_competition_tier", "")
    n = int(metrics.get("zaishishin_competitors") or metrics.get("home_visit_competitors") or 0)
    if tier == "外部競合・高":
        low *= 0.55
        high *= 0.65
        notes.append(f"在支診が圏内{n}院→期待シェア帯を下方調整")
    elif tier == "外部競合・中":
        low *= 0.75
        high *= 0.8
        notes.append(f"在支診が圏内{n}院→期待シェア帯をやや下方調整")
    elif tier == "外部競合・低〜中":
        low *= 0.9
        high *= 0.95
        notes.append(f"在支診が圏内{n}院")
    elif tier == "外部競合・低":
        low *= 1.05
        high *= 1.15
        notes.append(f"在支診が相対的に少ない（{n}院）→期待シェア帯をやや上方調整")
    return round(low, 2), round(high, 2), notes
