"""NDB年齢別受療率に基づく需要推計（home_visit_demand 連携）。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .geometry import circle_intersection_weight, haversine_km
from .data_loader import load_constants

# sibling package
_HVD_ROOT = Path(__file__).resolve().parents[3] / "home_visit_demand"
_HVD_SRC = _HVD_ROOT / "src"
_HVD_DATA = _HVD_ROOT / "data" / "processed"


@dataclass
class DemandEstimate:
    visit_patients_total: float
    visit_patients_home: float
    visit_patients_facility: float
    recommended_home_patients: float
    elderly_65: float
    home_share_used: float
    method: str
    age_bands: list[dict]
    notes: list[str]


def _load_hvd_json(name: str):
    path = _HVD_DATA / name
    if not path.exists():
        raise FileNotFoundError(f"home_visit_demand データがありません: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _pref_home_share(pref: str, default: float) -> float:
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "prefecture_home_shares.json"
    )
    if not path.exists():
        return default
    data = json.loads(path.read_text(encoding="utf-8"))
    rec = data.get("prefectures", {}).get(pref)
    if rec and rec.get("home_share") is not None:
        return float(rec["home_share"])
    return float(data.get("national", {}).get("home_share", default))


def estimate_demand_for_catchment(
    lat: float,
    lon: float,
    municipalities: Sequence,  # MunicipalityGeo
    *,
    radius_km: float = 8.0,
    prefer_prefecture_home_share: bool = True,
) -> DemandEstimate:
    """半径圏の需要を NDB 年齢別受療率で推計する。"""
    rates = _load_hvd_json("national_visit_rates.json")
    constants = _load_hvd_json("national_constants.json")
    mhlw = load_constants()
    default_share = float(mhlw["mix"]["home_share_of_visit_patients"])

    # weighted demographics via circle intersection
    elderly_65 = elderly_75 = elderly_65_74 = pop = 0.0
    pref_weight: dict[str, float] = {}
    for m in municipalities:
        d = haversine_km(lat, lon, m.lat, m.lon)
        w = circle_intersection_weight(d, radius_km, m.area_km2)
        if w <= 0:
            continue
        elderly_65 += m.elderly_65 * w
        elderly_75 += m.elderly_75 * w
        e6574 = max(0, m.elderly_65 - m.elderly_75)
        elderly_65_74 += e6574 * w
        pop += m.pop_total * w
        pref_weight[m.pref] = pref_weight.get(m.pref, 0.0) + w * m.elderly_65

    # expand age bands using national structure
    s6574 = constants["share_within_65_74"]
    s75 = constants["share_within_75plus"]
    age_pops = {
        "65-69": elderly_65_74 * s6574["65-69"],
        "70-74": elderly_65_74 * s6574["70-74"],
        "75-79": elderly_75 * s75["75-79"],
        "80-84": elderly_75 * s75["80-84"],
        "85-89": elderly_75 * s75["85-89"],
        "90+": elderly_75 * s75["90+"],
    }

    # weighted prefecture home share
    if prefer_prefecture_home_share and pref_weight:
        tw = sum(pref_weight.values()) or 1.0
        home_share = sum(
            _pref_home_share(p, default_share) * w for p, w in pref_weight.items()
        ) / tw
        share_note = "都道府県別NDB居宅シェア（高齢者重み付き）"
    else:
        home_share = default_share
        share_note = "全国NDB居宅シェア"

    bands = []
    patients_total = patients_home = patients_fac = 0.0
    for band, p in age_pops.items():
        rb = rates["age_bands"][band]
        pt = p * rb["patient_rate_total"]
        # Re-split home/facility using regional home_share while preserving total
        ph = pt * home_share
        pf = pt * (1.0 - home_share)
        patients_total += pt
        patients_home += ph
        patients_fac += pf
        bands.append(
            {
                "band": band,
                "population": round(p),
                "patients_total": round(pt, 1),
                "patients_home": round(ph, 1),
                "patients_facility": round(pf, 1),
            }
        )

    facility_residents = elderly_65 * constants["facility_residents_per_elderly_65"]
    home_residual = max(0.0, patients_total - patients_fac)
    recommended = (patients_home + home_residual) / 2.0

    return DemandEstimate(
        visit_patients_total=round(patients_total, 1),
        visit_patients_home=round(patients_home, 1),
        visit_patients_facility=round(patients_fac, 1),
        recommended_home_patients=round(recommended, 1),
        elderly_65=round(elderly_65, 1),
        home_share_used=round(home_share, 4),
        method="ndb_age_bands+regional_home_share+circle_intersection",
        age_bands=bands,
        notes=[
            "受療率: 第10回NDB年齢別在宅患者訪問診療料 ÷ 人口 ÷ 月1.90回",
            share_note,
            "キャッチメント重み: 等面積円交差",
            "推奨居宅 = (地域シェア居宅推計 + 総需要−施設需要残差) / 2",
        ],
    )
