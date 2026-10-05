"""施設点ベースの供給集計とグループ院の需要按分。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from .geometry import haversine_km
from .data_loader import load_constants

DATA = Path(__file__).resolve().parents[2] / "data" / "processed"

# 自グループを競合から除外するための名称パターン
OWN_GROUP_NAME_PATTERNS = (
    r"わかさクリニック",
    r"元気会",
    r"医療法人\s*元気会",
)


@dataclass
class FacilityPoint:
    id: str
    name: str
    lat: float
    lon: float
    facility_type: str  # home_support_clinic | home_support_hospital
    pref: str
    municipality: str
    enhanced: bool = False
    enhanced_kind: str = "unknown"  # solo|joint|standard|unknown


@dataclass
class PointSupply:
    clinics: float
    hospitals: float
    supply_units: float
    clinic_ids: List[str] = field(default_factory=list)
    hospital_ids: List[str] = field(default_factory=list)
    hospital_weight: float = 1.0
    method: str = "facility_points"
    clinic_enhanced: float = 0.0
    clinic_standard: float = 0.0
    hospital_enhanced: float = 0.0
    hospital_standard: float = 0.0
    excluded_own_group: int = 0


def is_own_group_facility(name: str, patterns: Sequence[str] = OWN_GROUP_NAME_PATTERNS) -> bool:
    if not name:
        return False
    for pat in patterns:
        if re.search(pat, name):
            return True
    return False


def load_facility_points() -> List[FacilityPoint]:
    path = DATA / "facility_points.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: List[FacilityPoint] = []
    for f in raw.get("facilities", []):
        if f.get("lat") is None or f.get("lon") is None:
            continue
        out.append(
            FacilityPoint(
                id=str(f["id"]),
                name=f.get("name", ""),
                lat=float(f["lat"]),
                lon=float(f["lon"]),
                facility_type=f.get("facility_type", "home_support_clinic"),
                pref=f.get("pref", ""),
                municipality=f.get("municipality", ""),
                enhanced=bool(f.get("enhanced", False)),
                enhanced_kind=str(f.get("enhanced_kind") or "unknown"),
            )
        )
    return out


def hospital_weight_for_prefs(prefs: Iterable[str]) -> float:
    path = DATA / "hospital_visit_weights.json"
    if not path.exists():
        return 1.0
    data = json.loads(path.read_text(encoding="utf-8"))
    weights = []
    for p in prefs:
        rec = data.get("prefectures", {}).get(p)
        if rec and rec.get("hospital_weight_vs_clinic"):
            weights.append(float(rec["hospital_weight_vs_clinic"]))
    if not weights:
        nat = data.get("prefectures", {}).get("全国", {})
        return float(nat.get("hospital_weight_vs_clinic") or 1.0)
    return sum(weights) / len(weights)


def count_facilities_in_radius(
    lat: float,
    lon: float,
    radius_km: float,
    facilities: Optional[Sequence[FacilityPoint]] = None,
    hospital_weight: Optional[float] = None,
    *,
    exclude_own_group: bool = True,
) -> PointSupply:
    facilities = list(facilities) if facilities is not None else load_facility_points()
    clinics: List[FacilityPoint] = []
    hospitals: List[FacilityPoint] = []
    prefs = set()
    excluded = 0
    for f in facilities:
        if haversine_km(lat, lon, f.lat, f.lon) > radius_km:
            continue
        if exclude_own_group and is_own_group_facility(f.name):
            excluded += 1
            continue
        prefs.add(f.pref)
        if f.facility_type == "home_support_hospital":
            hospitals.append(f)
        else:
            clinics.append(f)
    hw = hospital_weight if hospital_weight is not None else hospital_weight_for_prefs(prefs)
    c_enh = sum(1 for f in clinics if f.enhanced)
    c_std = len(clinics) - c_enh
    h_enh = sum(1 for f in hospitals if f.enhanced)
    h_std = len(hospitals) - h_enh
    units = len(clinics) + len(hospitals) * hw
    return PointSupply(
        clinics=float(len(clinics)),
        hospitals=float(len(hospitals)),
        supply_units=round(units, 2),
        clinic_ids=[f.id for f in clinics],
        hospital_ids=[f.id for f in hospitals],
        hospital_weight=round(hw, 3),
        method="facility_points",
        clinic_enhanced=float(c_enh),
        clinic_standard=float(c_std),
        hospital_enhanced=float(h_enh),
        hospital_standard=float(h_std),
        excluded_own_group=excluded,
    )


def group_overlap_shares(
    clinic_points: Sequence[tuple[str, float, float]],
    *,
    overlap_radius_km: float = 16.0,
) -> dict[str, float]:
    """同一グループ院が近接する場合の需要按分シェア（距離逆数、合計1）。"""
    n = len(clinic_points)
    if n == 0:
        return {}
    shares: dict[str, float] = {}
    for i, (name_i, lat_i, lon_i) in enumerate(clinic_points):
        weights = []
        for j, (name_j, lat_j, lon_j) in enumerate(clinic_points):
            d = haversine_km(lat_i, lon_i, lat_j, lon_j)
            if d <= overlap_radius_km:
                w = 1.0 / max(d, 0.5)
                weights.append(w)
        total = sum(weights) or 1.0
        self_w = 1.0 / 0.5
        shares[name_i] = self_w / total
    return shares


def adjusted_demand(
    regional_home: float,
    regional_total: float,
    clinic_name: str,
    clinic_points: Sequence[tuple[str, float, float]],
) -> tuple[float, float, float]:
    """グループ重複を補正した需要を返す (home, total, share)."""
    shares = group_overlap_shares(clinic_points)
    share = shares.get(clinic_name, 1.0)
    return regional_home * share, regional_total * share, share
