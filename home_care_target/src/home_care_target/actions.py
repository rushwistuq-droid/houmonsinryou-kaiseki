"""院別アクション設計: 実務KPI・居宅シフト・紹介経路実績。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .actuals_compare import load_actuals
from .pipeline import ClinicAnalysis, analyze_all_wakasa
from .referral import CHANNEL_LABELS, load_referral_funnel, resolve_referral


REFERRAL_PLAYBOOK = {
    "低（獲得しやすい）": [
        {"channel": "居宅介護支援（CM）", "share": 0.45, "note": "新規開拓の主戦場"},
        {"channel": "病院退院調整", "share": 0.35, "note": "地域連携室へ定期訪問"},
        {"channel": "訪問看護", "share": 0.20, "note": "看護→医師ルートをKPI化"},
    ],
    "中": [
        {"channel": "居宅介護支援（CM）", "share": 0.40, "note": "既存深度＋新規の選択と集中"},
        {"channel": "病院退院調整", "share": 0.35, "note": "退院時許諾の獲得率を追跡"},
        {"channel": "訪問看護", "share": 0.25, "note": "グループ訪看連携"},
    ],
    "高": [
        {"channel": "居宅介護支援（CM）", "share": 0.35, "note": "施設偏重から居宅CMへ"},
        {"channel": "病院退院調整", "share": 0.30, "note": "グループ内エリア分担"},
        {"channel": "訪問看護", "share": 0.25, "note": "紹介元の質を優先"},
        {"channel": "自院外来・施設転換", "share": 0.10, "note": "施設→居宅・外来在宅化"},
    ],
    "非常に高（シェア拡大が難しい）": [
        {"channel": "居宅介護支援（CM）", "share": 0.30, "note": "重症寄りに絞る"},
        {"channel": "病院退院調整", "share": 0.25, "note": "特定病院の固定ルート"},
        {"channel": "訪問看護", "share": 0.25, "note": "既存連携の維持"},
        {"channel": "自院外来・施設転換", "share": 0.20, "note": "自院パイプライン"},
    ],
}


@dataclass
class ClinicActionPlan:
    clinic: str
    alias: str
    priority: int
    competition_label: str
    actual_home: Optional[int]
    operational_kpi: int
    fair_share_kpi: int
    gap_to_operational: Optional[int]
    months: int
    monthly_new_to_operational: Optional[float]
    home_mix_band: Optional[str]
    home_shift_gap: Optional[int]
    status: str
    referral_source: str
    referral_mix: List[Dict[str, Any]]
    referral_monthly_by_channel: Dict[str, float]
    actions: List[str]
    ignore_for_priority: bool = False


def _playbook_key(label: str) -> str:
    if label.startswith("低"):
        return "低（獲得しやすい）"
    if label.startswith("非常に高"):
        return "非常に高（シェア拡大が難しい）"
    if label.startswith("高"):
        return "高"
    return "中"


def _priority_score(
    *,
    ignore: bool,
    home: Optional[int],
    op: int,
    mix_band: Optional[str],
    shift_gap: Optional[int],
) -> int:
    if ignore:
        return -1000
    if home is None:
        return 50
    if mix_band == "施設偏重" and shift_gap and shift_gap > 0:
        return 800 + shift_gap
    if home < op:
        return 500 + (op - home)
    return 10


def build_action_plans(
    *,
    analyses: Optional[List[ClinicAnalysis]] = None,
    months: int = 12,
    actuals_path: Optional[Path] = None,
) -> List[ClinicActionPlan]:
    try:
        actuals = load_actuals(actuals_path)
    except FileNotFoundError:
        actuals = {}
    analyses = analyses or analyze_all_wakasa(actuals=actuals)
    funnel = load_referral_funnel()

    drafts: List[tuple[int, ClinicActionPlan]] = []
    for a in analyses:
        act = actuals.get(a.clinic)
        home = int(act["home"]) if act else None
        g = a.growth
        op = a.operational_kpi_home
        ignore = bool(g.ignore_for_priority) if g else False
        mix_band = g.home_mix.band if g and g.home_mix else None
        shift_gap = g.home_mix.shift_gap_to_target if g and g.home_mix else None

        if ignore:
            status = "開院初期（優先対象外）"
            monthly = 0.0
        elif home is None:
            status = "実績未登録"
            monthly = None
        elif mix_band == "施設偏重" and shift_gap and shift_gap > 0:
            status = "居宅シフト要"
            monthly = shift_gap / months
        elif home < op:
            status = "実務KPI未達"
            monthly = (op - home) / months
        elif home >= (g.operational_stretch_home if g else op):
            status = "伸長以上（維持・質）"
            monthly = 0.0
        else:
            status = "実務KPI達成（伸長任意）"
            stretch = g.operational_stretch_home if g else op
            monthly = max(0.0, (stretch - home) / months)

        playbook = REFERRAL_PLAYBOOK[_playbook_key(a.acquisition.competition_label)]
        # 施設偏重はCM/自院転換を厚く
        if mix_band == "施設偏重":
            playbook = [
                {"channel": "居宅介護支援（CM）", "share": 0.45, "note": "居宅シフトの主戦場"},
                {"channel": "自院外来・施設転換", "share": 0.25, "note": "施設患者の居宅移行"},
                {"channel": "病院退院調整", "share": 0.20, "note": "退院→居宅"},
                {"channel": "訪問看護", "share": 0.10, "note": "居宅継続の受け皿"},
            ]

        ref = resolve_referral(
            a.clinic,
            a.alias,
            monthly_new_needed=monthly or 0.0,
            playbook=playbook,
            funnel=funnel,
        )
        # monthly quotas for display
        if ref.source == "actual" and ref.window_months:
            monthly_by = {
                k: round(v / ref.window_months, 2) for k, v in ref.by_channel.items()
            }
        else:
            monthly_by = {k: float(v) for k, v in ref.by_channel.items()}

        actions: List[str] = []
        if ignore:
            actions.append("開院初期のため優先リスト対象外（モニタリングのみ）")
        elif status == "居宅シフト要":
            actions.append(
                f"居宅比を目標まで上げるため、{months}ヶ月で月平均{monthly:.1f}人の居宅純増"
            )
            actions.append("施設偏重の紹介元を見直し、居宅CM比率を引き上げる")
        elif status == "実務KPI未達":
            actions.append(f"実務KPI {op} まで月平均{monthly:.1f}人の居宅新規")
        elif status.startswith("実務KPI達成"):
            actions.append("実務KPI達成。伸長は任意、紹介元の質を優先")
        else:
            actions.append("伸長超過。維持とグループ内重複整理")

        if ref.source == "actual":
            actions.extend(ref.notes)
        else:
            actions.append(ref.notes[0])
            # show channel quotas
            parts = [
                f"{CHANNEL_LABELS[k]} {v:.1f}"
                for k, v in monthly_by.items()
                if v and (monthly or 0) > 0
            ]
            if parts:
                actions.append("月次チャネル割当: " + " / ".join(parts))

        if a.acquisition.competition_label.startswith("高") and not ignore:
            actions.append("16km圏の自グループ院と退院調整・CMエリアを分担")

        plan = ClinicActionPlan(
            clinic=a.clinic,
            alias=a.alias,
            priority=0,
            competition_label=a.acquisition.competition_label,
            actual_home=home,
            operational_kpi=op,
            fair_share_kpi=a.kpi_target_home,
            gap_to_operational=(home - op) if home is not None else None,
            months=months,
            monthly_new_to_operational=round(monthly, 2) if monthly is not None else None,
            home_mix_band=mix_band,
            home_shift_gap=shift_gap,
            status=status,
            referral_source=ref.source,
            referral_mix=playbook,
            referral_monthly_by_channel=monthly_by,
            actions=actions,
            ignore_for_priority=ignore,
        )
        drafts.append(
            (
                _priority_score(
                    ignore=ignore,
                    home=home,
                    op=op,
                    mix_band=mix_band,
                    shift_gap=shift_gap,
                ),
                plan,
            )
        )

    drafts.sort(key=lambda x: -x[0])
    out: List[ClinicActionPlan] = []
    for i, (_, p) in enumerate(drafts, 1):
        p.priority = i
        out.append(p)
    return out


def public_action_summary(plans: List[ClinicActionPlan]) -> Dict[str, Any]:
    rows = []
    for p in plans:
        rows.append(
            {
                "priority": p.priority,
                "clinic": p.clinic,
                "alias": p.alias,
                "status": p.status,
                "ignore_for_priority": p.ignore_for_priority,
                "competition_label": p.competition_label,
                "operational_kpi": p.operational_kpi,
                "fair_share_kpi": p.fair_share_kpi,
                "home_mix_band": p.home_mix_band,
                "home_shift_gap": p.home_shift_gap,
                "monthly_new_to_operational": p.monthly_new_to_operational,
                "referral_source": p.referral_source,
                "referral_channels": [c["channel"] for c in p.referral_mix],
                "referral_monthly_by_channel": p.referral_monthly_by_channel,
                "actions": p.actions,
                "gap_sign": (
                    None
                    if p.gap_to_operational is None
                    else "over"
                    if p.gap_to_operational > 0
                    else "at"
                    if p.gap_to_operational == 0
                    else "under"
                ),
            }
        )
    return {"months": plans[0].months if plans else 12, "plans": rows}


def write_action_plans(
    confidential_path: Path,
    public_path: Path,
    *,
    months: int = 12,
) -> List[ClinicActionPlan]:
    plans = build_action_plans(months=months)
    confidential_path.parent.mkdir(parents=True, exist_ok=True)
    confidential_path.write_text(
        json.dumps({"plans": [asdict(p) for p in plans]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(public_action_summary(plans), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plans
