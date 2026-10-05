"""競合を本軸にした患者獲得指標。

背景
----
在支診・在支病の施設点数は供給ユニットとして既に集計している。
ただし「能力ティア目標」だけだと競合密度が目標に効かない。
本モジュールは需要÷実効競合を主軸に、能力・医師数で上限をかけた
獲得目標（attainable acquisition）を算出する。

実効競合（v0.4）
--------------
enhanced_clinics × 1.0 + standard_clinics × 0.35
+ hospitals × hospital_weight
+ extra_visit_units（在支診以外の訪問実施診の軽加算）
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .data_loader import load_constants


@dataclass
class AcquisitionIndicator:
    """患者獲得の実務指標一式。"""

    regional_home_demand: float
    regional_visit_demand: float
    competitors_clinics: float
    competitors_hospitals: float
    hospital_weight: float
    raw_supply_units: float
    effective_supply_units: float
    active_competitor_rate: float

    equilibrium_home: float
    competitive_home: float
    top_quartile_home: float
    market_share_equilibrium_pct: float
    market_share_competitive_pct: float

    capacity_cap_home: float
    fte_cap_home: Optional[float]

    acquisition_floor_home: int
    acquisition_target_home: int
    acquisition_stretch_home: int
    competition_index: float
    competition_label: str

    clinic_enhanced: float = 0.0
    clinic_standard: float = 0.0
    extra_visit_units: float = 0.0
    notes: list[str] = field(default_factory=list)
    assumptions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _competition_label(index: float) -> str:
    if index < 30:
        return "低（獲得しやすい）"
    if index < 55:
        return "中"
    if index < 75:
        return "高"
    return "非常に高（シェア拡大が難しい）"


def compute_acquisition_indicator(
    *,
    regional_home_demand: float,
    regional_visit_demand: float,
    competitors_clinics: float,
    competitors_hospitals: float,
    hospital_weight: float = 1.0,
    physician_fte: Optional[float] = None,
    local_avg_total_patients: Optional[float] = None,
    strategic_home_ratio: float = 0.60,
    active_competitor_rate: float = 0.45,
    top_quartile_multiplier: float = 2.5,
    ambition_multiplier: float = 1.35,
    clinic_enhanced: Optional[float] = None,
    clinic_standard: Optional[float] = None,
    hospital_enhanced: Optional[float] = None,
    hospital_standard: Optional[float] = None,
    extra_visit_units: float = 0.0,
    enhanced_clinic_rate: float = 1.0,
    standard_clinic_rate: float = 0.35,
) -> AcquisitionIndicator:
    """競合加味の獲得目標を計算する。

    核心式
    ------
    raw_units = clinics + hospitals * hospital_weight + extra
    effective_units =
        enhanced * enhanced_rate + standard * standard_rate
        + hospitals * hospital_weight + extra
    （enhanced/standard 未指定時は clinics × active_competitor_rate）
    """
    constants = load_constants()
    tiers = constants.get("capacity_tiers", {})
    activity = constants.get("competitor_activity", {})
    if enhanced_clinic_rate == 1.0 and "enhanced_clinic_rate" in activity:
        enhanced_clinic_rate = float(activity["enhanced_clinic_rate"])
    if standard_clinic_rate == 0.35 and "standard_clinic_rate" in activity:
        standard_clinic_rate = float(activity["standard_clinic_rate"])

    clinics = max(float(competitors_clinics), 0.0)
    hospitals = max(float(competitors_hospitals), 0.0)
    hw = float(hospital_weight)
    home = max(float(regional_home_demand), 0.0)
    visit = max(float(regional_visit_demand), home)
    extra = max(float(extra_visit_units), 0.0)

    if clinic_enhanced is None and clinic_standard is None:
        c_enh = 0.0
        c_std = clinics
        use_split = False
    else:
        c_enh = max(float(clinic_enhanced or 0.0), 0.0)
        c_std = max(float(clinic_standard if clinic_standard is not None else clinics - c_enh), 0.0)
        use_split = True

    raw_units = max(clinics + hospitals * hw + extra, 1.0)
    if use_split:
        effective_units = max(
            c_enh * enhanced_clinic_rate
            + c_std * standard_clinic_rate
            + hospitals * hw
            + extra,
            1.0,
        )
        rate_note = (
            f"機能強化型{c_enh:.0f}×{enhanced_clinic_rate:.2f}"
            f"+従来型{c_std:.0f}×{standard_clinic_rate:.2f}"
            f"+在支病×{hw:.2f}+訪問実施軽加算{extra:.1f}"
        )
        eff_rate_display = standard_clinic_rate
    else:
        effective_units = max(clinics * active_competitor_rate + hospitals * hw + extra, 1.0)
        rate_note = f"在支診×{active_competitor_rate:.0%}+在支病×{hw:.2f}+軽加算{extra:.1f}"
        eff_rate_display = active_competitor_rate

    equilibrium = home / raw_units
    competitive = home / effective_units
    top_q = competitive * top_quartile_multiplier

    specialty_total = float(tiers.get("specialty_p90_total", 150.0))
    enhanced_total = float(tiers.get("enhanced_proxy_total", 200.0))
    local_total = float(local_avg_total_patients) if local_avg_total_patients else specialty_total
    capacity_cap = max(local_total, specialty_total) * strategic_home_ratio
    stretch_cap = enhanced_total * strategic_home_ratio

    per_fte = float(tiers.get("physician_home_per_fte", 100.0))
    fte_cap = physician_fte * per_fte if physician_fte and physician_fte > 0 else None

    density = effective_units / max(home / 1000.0, 0.01)
    competition_index = max(0.0, min(100.0, (density - 5.0) / 45.0 * 100.0))

    uncapped_target = competitive * ambition_multiplier
    uncapped_stretch = top_q

    upper_target = capacity_cap
    upper_stretch = stretch_cap
    if fte_cap is not None:
        upper_target = min(upper_target, fte_cap)
        upper_stretch = min(upper_stretch, fte_cap * 1.25)

    if competition_index >= 75:
        uncapped_target = competitive * min(ambition_multiplier, 1.15)
        uncapped_stretch = competitive * min(top_quartile_multiplier, 1.8)

    floor = min(equilibrium, competitive)
    floor = min(floor, upper_target)
    target = max(floor, min(uncapped_target, upper_target))
    stretch = max(target, min(uncapped_stretch, upper_stretch))

    notes = [
        f"単純按分 = 居宅需要 {home:.0f} ÷ 生供給 {raw_units:.1f} = {equilibrium:.1f}",
        f"実効按分 = 居宅需要 {home:.0f} ÷ 実効競合 {effective_units:.1f} ({rate_note}) = {competitive:.1f}",
        f"獲得目標は実効按分×{ambition_multiplier:.2f}を能力/FTEで上限クリップ",
        "機能強化型を重く、従来型・非在支の訪問実施を軽く数える",
        f"競合指数 {competition_index:.0f}/100（需要1000人あたり実効競合 {density:.1f}）",
    ]
    if fte_cap is not None:
        notes.append(f"医師FTE上限 {fte_cap:.0f}人（{physician_fte}×{per_fte:.0f}）")

    return AcquisitionIndicator(
        regional_home_demand=round(home, 1),
        regional_visit_demand=round(visit, 1),
        competitors_clinics=round(clinics, 1),
        competitors_hospitals=round(hospitals, 1),
        hospital_weight=round(hw, 3),
        raw_supply_units=round(raw_units, 2),
        effective_supply_units=round(effective_units, 2),
        active_competitor_rate=eff_rate_display,
        equilibrium_home=round(equilibrium, 1),
        competitive_home=round(competitive, 1),
        top_quartile_home=round(top_q, 1),
        market_share_equilibrium_pct=round(100.0 * equilibrium / home, 3) if home else 0.0,
        market_share_competitive_pct=round(100.0 * competitive / home, 3) if home else 0.0,
        capacity_cap_home=round(capacity_cap, 1),
        fte_cap_home=round(fte_cap, 1) if fte_cap is not None else None,
        acquisition_floor_home=int(round(floor)),
        acquisition_target_home=int(round(target)),
        acquisition_stretch_home=int(round(stretch)),
        competition_index=round(competition_index, 1),
        competition_label=_competition_label(competition_index),
        clinic_enhanced=round(c_enh, 1),
        clinic_standard=round(c_std, 1),
        extra_visit_units=round(extra, 2),
        notes=notes,
        assumptions={
            "enhanced_clinic_rate": enhanced_clinic_rate,
            "standard_clinic_rate": standard_clinic_rate,
            "active_competitor_rate_fallback": active_competitor_rate,
            "extra_visit_units": extra,
            "top_quartile_multiplier": top_quartile_multiplier,
            "ambition_multiplier": ambition_multiplier,
            "strategic_home_ratio": strategic_home_ratio,
            "use_enhanced_split": use_split,
        },
    )
