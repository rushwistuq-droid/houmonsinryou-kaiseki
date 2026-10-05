"""単一院の需要・供給・獲得KPI・増分KPI・居宅ミックスを一括計算する本番接続層。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .acquisition import AcquisitionIndicator, compute_acquisition_indicator
from .catchment import CatchmentPoint, MunicipalityGeo, aggregate_catchment_supply
from .data_loader import load_constants
from .demand import estimate_demand_for_catchment
from .facilities import (
    adjusted_demand,
    count_facilities_in_radius,
    hospital_weight_for_prefs,
    load_facility_points,
)
from .growth import GrowthKpi, compute_growth_kpi
from .targets import HomePatientTargetResult, SupplySnapshot, compute_home_patient_targets
from .wakasa_demo_data import CLINIC_ALIASES, CLINICS, MUNICIPALITIES, PHYSICIAN_FTE


@dataclass
class ClinicAnalysis:
    clinic: str
    alias: str
    lat: float
    lon: float
    radius_km: float
    physician_fte: Optional[float]
    demand_home_raw: float
    demand_visit_raw: float
    demand_home_adjusted: float
    demand_visit_adjusted: float
    home_share: float
    group_overlap_share: float
    elderly_65: float
    competitors_clinics: float
    competitors_hospitals: float
    clinic_enhanced_est: float
    clinic_standard_est: float
    hospital_weight: float
    extra_visit_units: float
    excluded_own_group: int
    supply_method: str
    acquisition: AcquisitionIndicator
    capacity: HomePatientTargetResult
    growth: Optional[GrowthKpi]
    kpi_target_home: int
    capacity_cap_home: float
    fte_cap_home: Optional[float]
    operational_kpi_home: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["acquisition"] = self.acquisition.to_dict()
        d["capacity"] = self.capacity.to_dict()
        d["growth"] = self.growth.to_dict() if self.growth else None
        return d

    def management_row(self) -> Dict[str, Any]:
        g = self.growth
        return {
            "clinic": self.clinic,
            "alias": self.alias,
            "fair_share_kpi_home": self.kpi_target_home,
            "operational_kpi_home": self.operational_kpi_home,
            "operational_stretch_home": g.operational_stretch_home if g else self.acquisition.acquisition_stretch_home,
            "growth_mode": g.mode if g else "early",
            "acquisition_floor_home": self.acquisition.acquisition_floor_home,
            "acquisition_stretch_home": self.acquisition.acquisition_stretch_home,
            "capacity_cap_home": round(self.capacity_cap_home, 1),
            "capacity_specialty_home": self.capacity.capacity_specialty_home,
            "fte_cap_home": self.fte_cap_home,
            "headroom_to_capacity": g.headroom_to_capacity if g else None,
            "home_mix_band": g.home_mix.band if g and g.home_mix else None,
            "home_mix_share": g.home_mix.actual_home_share if g and g.home_mix else None,
            "home_shift_gap": g.home_mix.shift_gap_to_target if g and g.home_mix else None,
            "competition_label": self.acquisition.competition_label,
            "competition_index": self.acquisition.competition_index,
            "physician_fte": self.physician_fte,
            "excluded_own_group": self.excluded_own_group,
            "ignore_for_priority": bool(g.ignore_for_priority) if g else False,
        }


def resolve_clinic(
    clinic: Optional[str] = None,
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    name: Optional[str] = None,
    radius_km: float = 8.0,
) -> CatchmentPoint:
    if lat is not None and lon is not None:
        label = name or clinic or f"point_{lat:.4f}_{lon:.4f}"
        return CatchmentPoint(label, float(lat), float(lon), radius_km=radius_km)

    key = (clinic or name or "").strip()
    if not key:
        raise ValueError("clinic ID/name または lat/lon が必要です")

    full = CLINIC_ALIASES.get(key, key)
    for c in CLINICS:
        if c.name == full or c.name == key or key in c.name or full in c.name:
            return CatchmentPoint(c.name, c.lat, c.lon, radius_km=radius_km)

    for alias, fname in CLINIC_ALIASES.items():
        if key == alias or key in fname:
            for c in CLINICS:
                if c.name == fname:
                    return CatchmentPoint(c.name, c.lat, c.lon, radius_km=radius_km)

    raise KeyError(f"未知の院ID/名称: {key}")


def _alias_for(clinic_name: str) -> str:
    for alias, full in CLINIC_ALIASES.items():
        if full == clinic_name and alias not in ("リーフシティ市川",):
            return alias
    return clinic_name.replace("わかさクリニック", "").replace("リーフシティ", "")


def estimate_enhanced_split(
    clinics: float,
    hospitals: float,
    clinic_enhanced_abs: float,
    hospital_enhanced_abs: float,
    muni_clinics: float,
) -> Tuple[float, float, float, float]:
    if clinics <= 0:
        return 0.0, 0.0, float(hospitals), 0.0
    if clinic_enhanced_abs > 0 or (clinic_enhanced_abs == 0 and muni_clinics == 0):
        # prefer absolute facility-point enhanced counts when provided as already split
        pass
    if clinic_enhanced_abs >= 0 and (clinic_enhanced_abs + (clinics - clinic_enhanced_abs) == clinics):
        # If caller already passed point-level counts via clinic_enhanced_abs meaning enhanced count
        c_enh = min(clinics, max(0.0, clinic_enhanced_abs))
        c_std = max(0.0, clinics - c_enh)
    else:
        share = 0.0
        if muni_clinics > 0 and clinic_enhanced_abs > 0:
            share = min(1.0, clinic_enhanced_abs / muni_clinics)
        else:
            nat = load_constants().get("national", {})
            enh = float(nat.get("home_support_clinics_enhanced_2023_07") or 4120)
            tot = float(nat.get("home_support_clinics_notification_2023_07") or 14755)
            share = enh / tot if tot else 0.28
        c_enh = clinics * share
        c_std = max(0.0, clinics - c_enh)

    nat = load_constants().get("national", {})
    h_enh_n = float(nat.get("home_support_hospitals_enhanced_2023_07") or 782)
    h_tot = float(nat.get("home_support_hospitals_2023_07") or 2021)
    h_share = h_enh_n / h_tot if h_tot else 0.39
    if hospital_enhanced_abs > 0:
        h_enh = min(hospitals, hospital_enhanced_abs)
    else:
        h_enh = hospitals * h_share
    h_std = max(0.0, hospitals - h_enh)
    return c_enh, c_std, h_enh, h_std


def analyze_clinic(
    point: CatchmentPoint,
    *,
    municipalities: Optional[Sequence[MunicipalityGeo]] = None,
    group_points: Optional[Sequence[Tuple[str, float, float]]] = None,
    physician_fte: Optional[float] = None,
    prefer_points: bool = True,
    actual_home: Optional[int] = None,
    actual_facility: Optional[int] = None,
) -> ClinicAnalysis:
    munis = list(municipalities) if municipalities is not None else list(MUNICIPALITIES.values())
    clinic_xy = list(group_points) if group_points is not None else [(c.name, c.lat, c.lon) for c in CLINICS]
    fte = physician_fte if physician_fte is not None else PHYSICIAN_FTE.get(point.name)
    constants = load_constants()
    activity = constants.get("competitor_activity", {})
    ignore_set = set(constants.get("new_clinics_ignore_priority") or [])

    muni_supply = aggregate_catchment_supply(point, munis)
    prefs = set()
    for n in muni_supply.municipalities:
        geo = next((m for m in munis if m.name == n), None)
        if geo:
            prefs.add(geo.pref)
    hw = hospital_weight_for_prefs(prefs)

    demand = estimate_demand_for_catchment(point.lat, point.lon, munis, radius_km=point.radius_km)
    home_adj, total_adj, overlap = adjusted_demand(
        demand.recommended_home_patients,
        demand.visit_patients_total,
        point.name,
        clinic_xy,
    )

    excluded = 0
    points = load_facility_points() if prefer_points else []
    if prefer_points and points:
        point_supply = count_facilities_in_radius(
            point.lat,
            point.lon,
            point.radius_km,
            points,
            hospital_weight=hw,
            exclude_own_group=True,
        )
        excluded = point_supply.excluded_own_group
        snap = SupplySnapshot.from_point_supply(
            point_supply,
            elderly_65=demand.elderly_65,
            avg_patients=muni_supply.avg_patients_local_proxy,
            enhanced_clinics=point_supply.clinic_enhanced,
        )
        c_enh = point_supply.clinic_enhanced
        c_std = point_supply.clinic_standard
        h_enh = point_supply.hospital_enhanced
        h_std = point_supply.hospital_standard
        # 施設点に強化フラグが全く無い場合のみ市区町村比率へフォールバック
        marked_any = any(f.enhanced_kind not in ("unknown", "") for f in points)
        if not marked_any and point_supply.clinics > 0:
            c_enh, c_std, h_enh, h_std = estimate_enhanced_split(
                snap.home_support_clinics,
                snap.home_support_hospitals,
                muni_supply.clinic_enhanced,
                muni_supply.hospital_enhanced,
                muni_supply.home_support_clinics,
            )
        if point_supply.clinics + point_supply.hospitals < 1:
            snap = SupplySnapshot.from_catchment(muni_supply, hospital_weight=hw)
            snap.elderly_65 = demand.elderly_65
            c_enh, c_std, h_enh, h_std = estimate_enhanced_split(
                snap.home_support_clinics,
                snap.home_support_hospitals,
                muni_supply.clinic_enhanced,
                muni_supply.hospital_enhanced,
                muni_supply.home_support_clinics,
            )
    else:
        snap = SupplySnapshot.from_catchment(muni_supply, hospital_weight=hw)
        snap.elderly_65 = demand.elderly_65
        c_enh, c_std, h_enh, h_std = estimate_enhanced_split(
            snap.home_support_clinics,
            snap.home_support_hospitals,
            muni_supply.clinic_enhanced,
            muni_supply.hospital_enhanced,
            muni_supply.home_support_clinics,
        )

    snap.clinic_enhanced = c_enh
    snap.hospital_enhanced = h_enh
    extra_per = float(activity.get("non_zaitaku_visit_extra_per_clinic", 0.08))
    extra_units = snap.home_support_clinics * extra_per

    acq = compute_acquisition_indicator(
        regional_home_demand=home_adj,
        regional_visit_demand=total_adj,
        competitors_clinics=snap.home_support_clinics,
        competitors_hospitals=snap.home_support_hospitals,
        hospital_weight=snap.hospital_weight,
        physician_fte=fte,
        local_avg_total_patients=muni_supply.avg_patients_local_proxy,
        clinic_enhanced=c_enh,
        clinic_standard=c_std,
        hospital_enhanced=h_enh,
        hospital_standard=h_std,
        extra_visit_units=extra_units,
        enhanced_clinic_rate=float(activity.get("enhanced_clinic_rate", 1.0)),
        standard_clinic_rate=float(activity.get("standard_clinic_rate", 0.35)),
        active_competitor_rate=float(activity.get("active_competitor_rate_fallback", 0.45)),
    )

    capacity = compute_home_patient_targets(
        snap,
        regional_visit_patients=total_adj,
        regional_home_patients=home_adj,
        home_share=demand.home_share_used,
        physician_fte=fte,
        clinic_tier="specialty",
    )
    capacity.group_overlap_share = overlap

    growth = compute_growth_kpi(
        actual_home=actual_home,
        actual_facility=actual_facility,
        fair_share_kpi=acq.acquisition_target_home,
        fair_share_floor=acq.acquisition_floor_home,
        fair_share_stretch=acq.acquisition_stretch_home,
        capacity_cap_home=acq.capacity_cap_home,
        fte_cap_home=acq.fte_cap_home,
        ignore_for_priority=point.name in ignore_set,
    )

    return ClinicAnalysis(
        clinic=point.name,
        alias=_alias_for(point.name),
        lat=point.lat,
        lon=point.lon,
        radius_km=point.radius_km,
        physician_fte=fte,
        demand_home_raw=round(demand.recommended_home_patients, 1),
        demand_visit_raw=round(demand.visit_patients_total, 1),
        demand_home_adjusted=round(home_adj, 1),
        demand_visit_adjusted=round(total_adj, 1),
        home_share=demand.home_share_used,
        group_overlap_share=round(overlap, 3),
        elderly_65=round(demand.elderly_65, 1),
        competitors_clinics=snap.home_support_clinics,
        competitors_hospitals=snap.home_support_hospitals,
        clinic_enhanced_est=round(c_enh, 1),
        clinic_standard_est=round(c_std, 1),
        hospital_weight=snap.hospital_weight,
        extra_visit_units=round(extra_units, 2),
        excluded_own_group=excluded,
        supply_method=snap.supply_method,
        acquisition=acq,
        capacity=capacity,
        growth=growth,
        kpi_target_home=acq.acquisition_target_home,
        capacity_cap_home=acq.capacity_cap_home,
        fte_cap_home=acq.fte_cap_home,
        operational_kpi_home=growth.operational_kpi_home,
        notes=list(acq.notes) + list(growth.notes),
    )


def analyze_all_wakasa(
    *,
    prefer_points: bool = True,
    actuals: Optional[Dict[str, dict]] = None,
) -> List[ClinicAnalysis]:
    out = []
    for c in CLINICS:
        act = (actuals or {}).get(c.name)
        out.append(
            analyze_clinic(
                c,
                prefer_points=prefer_points,
                actual_home=act["home"] if act else None,
                actual_facility=act["facility"] if act else None,
            )
        )
    return out
