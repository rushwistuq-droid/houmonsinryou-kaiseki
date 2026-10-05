"""在支診・在支病の供給スナップショットと居宅患者目標の算出（精度強化版）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .catchment import CatchmentSupply
from .data_loader import load_constants
from .facilities import PointSupply


@dataclass
class SupplySnapshot:
    home_support_clinics: float
    home_support_hospitals: float
    supply_units: float
    clinic_enhanced: float = 0.0
    hospital_enhanced: float = 0.0
    avg_patients_per_clinic: Optional[float] = None
    patients_managed_total: Optional[float] = None
    elderly_65: Optional[float] = None
    hospital_weight: float = 1.0
    supply_method: str = "municipal_weighted"
    sources: list[str] = field(default_factory=list)

    @classmethod
    def from_catchment(cls, supply: CatchmentSupply, hospital_weight: float = 1.0) -> "SupplySnapshot":
        return cls(
            home_support_clinics=supply.home_support_clinics,
            home_support_hospitals=supply.home_support_hospitals,
            supply_units=supply.home_support_clinics
            + supply.home_support_hospitals * hospital_weight,
            clinic_enhanced=supply.clinic_enhanced,
            hospital_enhanced=supply.hospital_enhanced,
            avg_patients_per_clinic=supply.avg_patients_local_proxy,
            patients_managed_total=supply.patients_managed_proxy,
            elderly_65=supply.weighted_elderly_65,
            hospital_weight=hospital_weight,
            supply_method="municipal_circle_intersection",
            sources=list(supply.sources),
        )

    @classmethod
    def from_point_supply(
        cls,
        point: PointSupply,
        *,
        elderly_65: Optional[float] = None,
        avg_patients: Optional[float] = None,
        enhanced_clinics: float = 0.0,
    ) -> "SupplySnapshot":
        c_enh = point.clinic_enhanced if point.clinic_enhanced else enhanced_clinics
        return cls(
            home_support_clinics=point.clinics,
            home_support_hospitals=point.hospitals,
            supply_units=point.supply_units,
            clinic_enhanced=c_enh,
            hospital_enhanced=point.hospital_enhanced,
            elderly_65=elderly_65,
            avg_patients_per_clinic=avg_patients,
            hospital_weight=point.hospital_weight,
            supply_method=point.method,
            sources=["JMAP施設点 + 国土地理院ジオコード", "医療施設調査訪問件数ウェイト"],
        )


@dataclass
class HomePatientTargetResult:
    regional_visit_patients: float
    regional_home_patients: float
    home_share: float
    home_support_clinics: float
    home_support_hospitals: float
    supply_units: float
    fair_share_home: int
    capacity_baseline_home: int
    capacity_active_home: int
    capacity_local_home: Optional[int]
    capacity_enhanced_home: int
    capacity_specialty_home: int
    recommended_short_term_home: int
    recommended_mid_term_home: int
    recommended_stretch_home: int
    fair_share_total: int
    capacity_baseline_total: int
    capacity_active_total: int
    density_clinics_per_100k_elderly: Optional[float]
    group_overlap_share: Optional[float] = None
    supply_method: str = ""
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    assumptions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_home_patient_targets(
    supply: SupplySnapshot,
    *,
    regional_visit_patients: Optional[float] = None,
    regional_home_patients: Optional[float] = None,
    home_share: Optional[float] = None,
    strategic_home_ratio: float = 0.60,
    physician_fte: Optional[float] = None,
    group_overlap_share: Optional[float] = None,
    clinic_tier: str = "specialty",  # standard | active | specialty | enhanced
) -> HomePatientTargetResult:
    """
    供給×需要から居宅患者目標を算出。

    clinic_tier:
      - standard: 一般在支診平均
      - active: 患者20人以上の実働層
      - specialty: 訪問特化（150人前後）を短期に採用
      - enhanced: 機能強化型代理（200人）を中期に強く反映
    """
    constants = load_constants()
    mix = constants["mix"]
    cap = constants["capacity_benchmarks"]
    tiers = constants.get("capacity_tiers", {})
    demand_fb = constants["demand_fallback"]
    if home_share is None:
        home_share = float(mix["home_share_of_visit_patients"])

    notes: list[str] = []
    if regional_home_patients is not None and regional_visit_patients is None:
        visit = float(regional_home_patients) / max(home_share, 1e-6)
        home = float(regional_home_patients)
        notes.append("居宅需要の外部/NDB推計入力を使用")
    elif regional_visit_patients is not None:
        visit = float(regional_visit_patients)
        home = (
            float(regional_home_patients)
            if regional_home_patients is not None
            else visit * home_share
        )
        notes.append("訪問診療需要入力を使用")
    else:
        if not supply.elderly_65:
            raise ValueError("需要または elderly_65 が必要です")
        visit = float(supply.elderly_65) * float(demand_fb["elderly65_visit_rate"])
        home = visit * home_share
        notes.append("需要フォールバック: 65歳×4.5%×居宅シェア")

    if group_overlap_share is not None and 0 < group_overlap_share < 1.5:
        home *= group_overlap_share
        visit *= group_overlap_share
        notes.append(f"グループ院近接による需要按分シェア {group_overlap_share:.2f} を適用")

    units = max(float(supply.supply_units), 1.0)
    fair_total = visit / units
    fair_home = home / units

    baseline_total = float(tiers.get("standard_mean_total", cap["t108_mean_patients"]))
    active_total = float(tiers.get("active_mean_total", cap["active_mean_patients_ge20"]))
    enhanced_total = float(tiers.get("enhanced_proxy_total", cap["enhanced_proxy_patients"]))
    specialty_total = float(tiers.get("specialty_p90_total", 150.0))
    local_total = supply.avg_patients_per_clinic

    baseline_home = baseline_total * strategic_home_ratio
    active_home = active_total * strategic_home_ratio
    enhanced_home = enhanced_total * strategic_home_ratio
    specialty_home = specialty_total * strategic_home_ratio
    local_home = local_total * strategic_home_ratio if local_total is not None else None

    # tier-based recommendations
    if clinic_tier == "standard":
        short, mid, stretch = baseline_home, active_home, specialty_home
    elif clinic_tier == "active":
        short, mid, stretch = active_home, max(active_home, local_home or active_home), specialty_home
    elif clinic_tier == "enhanced":
        short, mid, stretch = specialty_home, enhanced_home, enhanced_home * 1.1
    else:  # specialty (わかさ型の既定)
        short = max(active_home, specialty_home * 0.7)
        mid = max(short, local_home or specialty_home, specialty_home)
        stretch = enhanced_home

    if local_home is not None:
        notes.append(
            f"二次医療圏平均 {local_total:.1f}人 × 戦略居宅比 {strategic_home_ratio:.0%} を反映"
        )
    notes.append(
        f"市場按分（参照）居宅 {fair_home:.0f}人 / 供給手法={supply.supply_method} / "
        f"病院ウェイト={supply.hospital_weight:.2f}"
    )
    notes.append(f"運営ティア={clinic_tier}")

    per_fte = float(tiers.get("physician_home_per_fte", 100.0))
    if physician_fte and physician_fte > 0:
        short = min(short, physician_fte * per_fte)
        mid = min(mid, physician_fte * per_fte * 1.2)
        stretch = min(stretch, physician_fte * per_fte * 1.5)
        notes.append(f"医師FTE {physician_fte} × {per_fte:.0f}人/FTE 上限を適用")

    density = None
    if supply.elderly_65 and supply.elderly_65 > 0:
        density = supply.home_support_clinics / supply.elderly_65 * 100_000

    sources = list(supply.sources) + [
        constants["sources"]["medical_facility_survey_r5"]["name"],
        constants["sources"]["facility_standard_notifications"]["name"],
        "第10回NDBオープンデータ（年齢別受療率・都道府県別居宅シェア）",
    ]

    return HomePatientTargetResult(
        regional_visit_patients=round(visit, 1),
        regional_home_patients=round(home, 1),
        home_share=home_share,
        home_support_clinics=supply.home_support_clinics,
        home_support_hospitals=supply.home_support_hospitals,
        supply_units=round(units, 2),
        fair_share_home=int(round(fair_home)),
        capacity_baseline_home=int(round(baseline_home)),
        capacity_active_home=int(round(active_home)),
        capacity_local_home=int(round(local_home)) if local_home is not None else None,
        capacity_enhanced_home=int(round(enhanced_home)),
        capacity_specialty_home=int(round(specialty_home)),
        recommended_short_term_home=int(round(short)),
        recommended_mid_term_home=int(round(mid)),
        recommended_stretch_home=int(round(stretch)),
        fair_share_total=int(round(fair_total)),
        capacity_baseline_total=int(round(baseline_total)),
        capacity_active_total=int(round(active_total)),
        density_clinics_per_100k_elderly=round(density, 1) if density is not None else None,
        group_overlap_share=group_overlap_share,
        supply_method=supply.supply_method,
        notes=notes,
        sources=sources,
        assumptions={
            "strategic_home_ratio": strategic_home_ratio,
            "market_home_share": home_share,
            "clinic_tier": clinic_tier,
            "hospital_weight": supply.hospital_weight,
            "specialty_total": specialty_total,
            "enhanced_total": enhanced_total,
        },
    )
