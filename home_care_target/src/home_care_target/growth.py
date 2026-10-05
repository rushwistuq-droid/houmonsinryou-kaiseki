"""成熟院向け増分KPIと居宅ミックス目標。

背景
----
競合按分の獲得KPIは「公平シェア」であり、成熟院は当然大きく超過する。
実務の本命は:
  1) 実績居宅からの増分（growth）
  2) 能力・FTE余力
  3) 施設偏重院の居宅比率シフト
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .data_loader import load_constants


@dataclass
class HomeMixTarget:
    actual_home: int
    actual_facility: int
    actual_total: int
    actual_home_share: float
    target_home_share: float
    stretch_home_share: float
    peer_benchmark_share: float
    home_at_target_share: int
    home_at_stretch_share: int
    shift_gap_to_target: int  # 追加で必要な居宅（比率目標）
    shift_gap_to_stretch: int
    band: str  # 施設偏重 / 標準 / 居宅寄り
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GrowthKpi:
    """成熟院向けの実務KPI。"""

    mode: str  # early | mature | hybrid
    actual_home: Optional[int]
    fair_share_kpi: int  # 旧・獲得KPI（参照）
    fair_share_floor: int
    fair_share_stretch: int
    annual_increment: int
    growth_target_home: int  # 本命: 実績+増分を能力で上限
    growth_stretch_home: int
    capacity_cap_home: float
    fte_cap_home: Optional[float]
    headroom_to_capacity: Optional[int]
    operational_kpi_home: int  # 経営が追う短期目標
    operational_stretch_home: int
    home_mix: Optional[HomeMixTarget] = None
    ignore_for_priority: bool = False  # 開院直後など
    notes: list[str] = field(default_factory=list)
    assumptions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.home_mix:
            d["home_mix"] = self.home_mix.to_dict()
        return d


def _mix_band(share: float, target: float) -> str:
    if share < target - 0.08:
        return "施設偏重"
    if share >= target + 0.08:
        return "居宅寄り"
    return "標準"


def compute_home_mix_target(
    *,
    actual_home: int,
    actual_facility: int,
    target_home_share: Optional[float] = None,
    stretch_home_share: Optional[float] = None,
    peer_benchmark_share: Optional[float] = None,
) -> HomeMixTarget:
    constants = load_constants()
    mix_cfg = constants.get("home_mix_targets", {})
    target = float(target_home_share if target_home_share is not None else mix_cfg.get("target_share", 0.40))
    stretch = float(
        stretch_home_share if stretch_home_share is not None else mix_cfg.get("stretch_share", 0.50)
    )
    peer = float(
        peer_benchmark_share
        if peer_benchmark_share is not None
        else mix_cfg.get("peer_benchmark_share", 0.55)
    )
    total = max(int(actual_home) + int(actual_facility), 0)
    share = (actual_home / total) if total else 0.0
    at_target = int(round(total * target)) if total else int(actual_home)
    at_stretch = int(round(total * stretch)) if total else int(actual_home)
    gap_t = max(0, at_target - actual_home)
    gap_s = max(0, at_stretch - actual_home)
    band = _mix_band(share, target)
    notes = [
        f"実績居宅比 {share:.0%}（居宅{actual_home}/合計{total}）",
        f"目標居宅比 {target:.0%} → 居宅{at_target}人（ギャップ{gap_t}）",
        f"伸長居宅比 {stretch:.0%}（ピア目安 {peer:.0%}）",
    ]
    if band == "施設偏重":
        notes.append("施設偏重: 居宅CM・退院調整へのシフトを優先")
    return HomeMixTarget(
        actual_home=actual_home,
        actual_facility=actual_facility,
        actual_total=total,
        actual_home_share=round(share, 3),
        target_home_share=target,
        stretch_home_share=stretch,
        peer_benchmark_share=peer,
        home_at_target_share=at_target,
        home_at_stretch_share=at_stretch,
        shift_gap_to_target=gap_t,
        shift_gap_to_stretch=gap_s,
        band=band,
        notes=notes,
    )


def compute_growth_kpi(
    *,
    actual_home: Optional[int],
    actual_facility: Optional[int] = None,
    fair_share_kpi: int,
    fair_share_floor: int,
    fair_share_stretch: int,
    capacity_cap_home: float,
    fte_cap_home: Optional[float] = None,
    annual_increment: Optional[int] = None,
    ignore_for_priority: bool = False,
) -> GrowthKpi:
    constants = load_constants()
    gcfg = constants.get("growth_kpi", {})
    inc = int(
        annual_increment
        if annual_increment is not None
        else gcfg.get("annual_home_increment_default", 24)
    )
    stretch_inc = int(gcfg.get("annual_home_increment_stretch", 36))

    home_mix = None
    if actual_home is not None and actual_facility is not None:
        home_mix = compute_home_mix_target(
            actual_home=int(actual_home), actual_facility=int(actual_facility)
        )
        # 施設偏重院は増分を居宅シフトギャップと連動（大きい方）
        if home_mix.band == "施設偏重":
            inc = max(inc, min(home_mix.shift_gap_to_target, int(gcfg.get("max_shift_increment", 48))))
            stretch_inc = max(stretch_inc, min(home_mix.shift_gap_to_stretch, 72))

    caps = [capacity_cap_home]
    if fte_cap_home is not None:
        caps.append(fte_cap_home)
    hard_cap = min(caps)

    notes: list[str] = []
    if actual_home is None:
        mode = "early"
        growth_target = fair_share_kpi
        growth_stretch = fair_share_stretch
        operational = fair_share_kpi
        operational_stretch = fair_share_stretch
        headroom = int(round(hard_cap - fair_share_kpi)) if hard_cap else None
        notes.append("実績なしのため公平シェア獲得KPIを短期目標に使用")
    else:
        ah = int(actual_home)
        if ah < fair_share_floor:
            mode = "early"
            growth_target = max(fair_share_kpi, ah + inc)
            growth_stretch = max(fair_share_stretch, ah + stretch_inc)
            notes.append("フロア未達: 獲得KPIと増分の大きい方を目標")
        elif ah < fair_share_kpi:
            mode = "hybrid"
            growth_target = fair_share_kpi
            growth_stretch = max(fair_share_stretch, ah + stretch_inc)
            notes.append("獲得KPI未達: 公平シェア目標を維持")
        else:
            mode = "mature"
            growth_target = ah + inc
            growth_stretch = ah + stretch_inc
            notes.append(f"成熟院: 実績{ah} + 年次増分{inc}を本命KPI")

        # 居宅シフト目標も考慮（比率ギャップがある場合は少なくともそこへ）
        if home_mix and home_mix.shift_gap_to_target > 0 and mode != "early":
            mix_target = ah + home_mix.shift_gap_to_target
            if mix_target > growth_target:
                growth_target = mix_target
                notes.append(
                    f"居宅比シフトを反映: 目標居宅{home_mix.home_at_target_share}"
                    f"（比{home_mix.target_home_share:.0%}）"
                )

        # 能力上限: 既に超過している場合は「維持」を目標にする（下方修正しない）
        if ah >= hard_cap:
            growth_target = ah
            growth_stretch = max(ah, int(round(min(ah + stretch_inc, hard_cap * 1.15))))
            notes.append("能力上限以上: 実務KPIは維持（増員・効率化で余力を作る）")
        else:
            growth_target = int(round(min(growth_target, hard_cap)))
            growth_stretch = int(round(min(max(growth_stretch, growth_target), hard_cap * 1.15)))

        operational = growth_target
        operational_stretch = growth_stretch
        headroom = max(0, int(round(hard_cap - ah)))

    return GrowthKpi(
        mode=mode,
        actual_home=actual_home,
        fair_share_kpi=fair_share_kpi,
        fair_share_floor=fair_share_floor,
        fair_share_stretch=fair_share_stretch,
        annual_increment=inc,
        growth_target_home=int(growth_target),
        growth_stretch_home=int(growth_stretch),
        capacity_cap_home=round(capacity_cap_home, 1),
        fte_cap_home=fte_cap_home,
        headroom_to_capacity=headroom,
        operational_kpi_home=int(operational),
        operational_stretch_home=int(operational_stretch),
        home_mix=home_mix,
        ignore_for_priority=ignore_for_priority,
        notes=notes,
        assumptions={
            "annual_home_increment_default": gcfg.get("annual_home_increment_default", 24),
            "home_mix_target_share": (home_mix.target_home_share if home_mix else None),
        },
    )
