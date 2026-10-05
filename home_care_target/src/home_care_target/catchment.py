"""地域キャッチメント内の在支診・在支病集計."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .data_loader import (
    avg_patients_per_clinic,
    get_municipal_facilities,
    get_prefecture_clinic_stats,
    get_secondary_clinic_stats,
    load_constants,
)
from .geometry import circle_intersection_weight, haversine_km, legacy_centroid_weight


@dataclass
class MunicipalityGeo:
    name: str
    pref: str
    lat: float
    lon: float
    area_km2: float
    elderly_65: int = 0
    elderly_75: int = 0
    pop_total: int = 0
    secondary_area_code: Optional[str] = None
    secondary_area_name: Optional[str] = None


@dataclass
class CatchmentPoint:
    name: str
    lat: float
    lon: float
    radius_km: float = 8.0


@dataclass
class CatchmentSupply:
    point: CatchmentPoint
    municipalities: List[str]
    home_support_clinics: float
    home_support_hospitals: float
    clinic_enhanced: float
    clinic_standard: float
    hospital_enhanced: float
    hospital_standard: float
    backup_hospitals: float
    weighted_elderly_65: float
    supply_units: float
    patients_managed_proxy: Optional[float]
    avg_patients_local_proxy: Optional[float]
    secondary_area_stats: Dict[str, dict] = field(default_factory=dict)
    prefecture_stats: Dict[str, dict] = field(default_factory=dict)
    details: List[dict] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)


def _facility_breakdown(name: str) -> Dict[str, float]:
    rec = get_municipal_facilities(name) or {}
    clinics = float(rec.get("home_support_clinics") or 0)
    hospitals = float(rec.get("home_support_hospitals") or 0)
    c_enh = float(
        (rec.get("clinic_enhanced_solo") or 0) + (rec.get("clinic_enhanced_joint") or 0)
    )
    c_std = float(rec.get("clinic_standard") or max(0.0, clinics - c_enh))
    h_enh = float(
        (rec.get("hospital_enhanced_solo") or 0)
        + (rec.get("hospital_enhanced_joint") or 0)
    )
    h_std = float(rec.get("hospital_standard") or max(0.0, hospitals - h_enh))
    backup = float(rec.get("backup_hospitals") or 0)
    return {
        "clinics": clinics,
        "hospitals": hospitals,
        "clinic_enhanced": c_enh,
        "clinic_standard": c_std,
        "hospital_enhanced": h_enh,
        "hospital_standard": h_std,
        "backup_hospitals": backup,
        "source": rec.get("source", "unknown"),
    }


def aggregate_catchment_supply(
    point: CatchmentPoint,
    municipalities: Sequence[MunicipalityGeo],
    hospital_weight: Optional[float] = None,
    weight_method: str = "circle_intersection",
) -> CatchmentSupply:
    """半径内自治体の在支診・在支病を距離重み付きで精密集計する。"""
    constants = load_constants()
    if hospital_weight is None:
        hospital_weight = float(constants["supply_weights"]["home_support_hospital"])

    weight_fn = (
        circle_intersection_weight
        if weight_method == "circle_intersection"
        else legacy_centroid_weight
    )

    details: List[dict] = []
    sources = set()
    totals = {
        "clinics": 0.0,
        "hospitals": 0.0,
        "clinic_enhanced": 0.0,
        "clinic_standard": 0.0,
        "hospital_enhanced": 0.0,
        "hospital_standard": 0.0,
        "backup_hospitals": 0.0,
        "elderly": 0.0,
        "patients_proxy": 0.0,
        "patients_weight": 0.0,
    }
    secondary_stats: Dict[str, dict] = {}
    prefecture_stats: Dict[str, dict] = {}

    for muni in municipalities:
        dist = haversine_km(point.lat, point.lon, muni.lat, muni.lon)
        w = weight_fn(dist, point.radius_km, muni.area_km2)
        if w <= 0:
            continue
        fac = _facility_breakdown(muni.name)
        sources.add(str(fac["source"]))
        totals["clinics"] += fac["clinics"] * w
        totals["hospitals"] += fac["hospitals"] * w
        totals["clinic_enhanced"] += fac["clinic_enhanced"] * w
        totals["clinic_standard"] += fac["clinic_standard"] * w
        totals["hospital_enhanced"] += fac["hospital_enhanced"] * w
        totals["hospital_standard"] += fac["hospital_standard"] * w
        totals["backup_hospitals"] += fac["backup_hospitals"] * w
        totals["elderly"] += muni.elderly_65 * w

        sec = None
        if muni.secondary_area_code:
            sec = get_secondary_clinic_stats(muni.secondary_area_code)
        if sec is None and muni.secondary_area_name:
            sec = get_secondary_clinic_stats(muni.secondary_area_name)
        if sec:
            secondary_stats[sec["code"]] = sec
            avg = avg_patients_per_clinic(sec)
            if avg is not None:
                totals["patients_proxy"] += fac["clinics"] * w * avg
                totals["patients_weight"] += fac["clinics"] * w

        pref = get_prefecture_clinic_stats(muni.pref)
        if pref:
            prefecture_stats[muni.pref] = pref

        details.append(
            {
                "municipality": muni.name,
                "pref": muni.pref,
                "distance_km": round(dist, 2),
                "weight": round(w, 3),
                "home_support_clinics": fac["clinics"],
                "home_support_hospitals": fac["hospitals"],
                "weighted_clinics": round(fac["clinics"] * w, 2),
                "weighted_hospitals": round(fac["hospitals"] * w, 2),
                "clinic_enhanced": fac["clinic_enhanced"],
                "hospital_enhanced": fac["hospital_enhanced"],
            }
        )

    details.sort(key=lambda x: x["distance_km"])
    supply_units = totals["clinics"] + totals["hospitals"] * hospital_weight
    avg_local = (
        totals["patients_proxy"] / totals["patients_weight"]
        if totals["patients_weight"] > 0
        else None
    )

    return CatchmentSupply(
        point=point,
        municipalities=[d["municipality"] for d in details],
        home_support_clinics=round(totals["clinics"], 2),
        home_support_hospitals=round(totals["hospitals"], 2),
        clinic_enhanced=round(totals["clinic_enhanced"], 2),
        clinic_standard=round(totals["clinic_standard"], 2),
        hospital_enhanced=round(totals["hospital_enhanced"], 2),
        hospital_standard=round(totals["hospital_standard"], 2),
        backup_hospitals=round(totals["backup_hospitals"], 2),
        weighted_elderly_65=round(totals["elderly"], 1),
        supply_units=round(supply_units, 2),
        patients_managed_proxy=round(totals["patients_proxy"], 1)
        if totals["patients_weight"] > 0
        else None,
        avg_patients_local_proxy=round(avg_local, 1) if avg_local is not None else None,
        secondary_area_stats=secondary_stats,
        prefecture_stats=prefecture_stats,
        details=details,
        sources=sorted(sources) + [f"weight_method={weight_method}"],
    )


def compute_regional_supply(municipalities: Iterable[str]) -> Dict[str, float]:
    """市区町村名リストの在支診・在支病を単純合算（重みなし）。"""
    clinics = hospitals = enh_c = enh_h = 0.0
    for name in municipalities:
        fac = _facility_breakdown(name)
        clinics += fac["clinics"]
        hospitals += fac["hospitals"]
        enh_c += fac["clinic_enhanced"]
        enh_h += fac["hospital_enhanced"]
    return {
        "home_support_clinics": clinics,
        "home_support_hospitals": hospitals,
        "clinic_enhanced": enh_c,
        "hospital_enhanced": enh_h,
        "supply_units": clinics + hospitals,
    }
