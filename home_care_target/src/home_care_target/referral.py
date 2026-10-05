"""紹介経路（CM / 病院 / 訪看）の実績接続。

機密YAMLがあれば実数、なければプレイブック比率×必要月次新規で割当。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wakasa_demo_data import CLINIC_ALIASES

DEFAULT_FUNNEL = (
    Path(__file__).resolve().parents[3]
    / "analysis"
    / "confidential"
    / "referral_funnel.yaml"
)

CHANNELS = ("cm", "hospital", "visit_nursing", "other")
CHANNEL_LABELS = {
    "cm": "居宅介護支援（CM）",
    "hospital": "病院退院調整",
    "visit_nursing": "訪問看護",
    "other": "その他・自院転換",
}


@dataclass
class ReferralActuals:
    clinic: str
    alias: str
    window_months: int
    by_channel: Dict[str, int]
    total_new_home: int
    source: str  # actual | estimated
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_funnel_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _parse_simple_funnel(text)


def _parse_simple_funnel(text: str) -> dict:
    """Minimal parser for referral_funnel.yaml shape."""
    clinics: List[dict] = []
    current: Optional[dict] = None
    in_channels = False
    meta: Dict[str, Any] = {"clinics": clinics}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("clinics:"):
            continue
        if line.strip().startswith("- alias:"):
            if current:
                clinics.append(current)
            current = {
                "alias": line.split(":", 1)[1].strip(),
                "new_home_by_channel": {},
            }
            in_channels = False
            continue
        if current is None:
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
            continue
        stripped = line.strip()
        if stripped.startswith("new_home_by_channel:"):
            in_channels = True
            continue
        if stripped.startswith("window_months:"):
            current["window_months"] = int(stripped.split(":", 1)[1].strip())
            in_channels = False
            continue
        if in_channels and ":" in stripped:
            k, v = stripped.split(":", 1)
            current["new_home_by_channel"][k.strip()] = int(v.strip())
            continue
        if ":" in stripped and not stripped.startswith("-"):
            k, v = stripped.split(":", 1)
            if k.strip() == "alias":
                current["alias"] = v.strip()
            else:
                current[k.strip()] = v.strip()
    if current:
        clinics.append(current)
    return meta


def load_referral_funnel(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or DEFAULT_FUNNEL
    if not path.exists():
        return {}
    raw = _parse_funnel_yaml(path.read_text(encoding="utf-8"))
    out: Dict[str, dict] = {}
    for row in raw.get("clinics") or []:
        alias = str(row["alias"])
        full = CLINIC_ALIASES.get(alias, alias)
        ch = row.get("new_home_by_channel") or {}
        out[full] = {
            "alias": alias,
            "window_months": int(row.get("window_months") or raw.get("default_window_months") or 3),
            "by_channel": {k: int(ch.get(k, 0)) for k in CHANNELS},
        }
    return out


def allocate_channel_quotas(
    monthly_new_needed: float,
    playbook: List[Dict[str, Any]],
) -> Dict[str, float]:
    """プレイブック share で月次新規をチャネル割当。"""
    label_to_key = {
        "居宅介護支援（CM）": "cm",
        "病院退院調整": "hospital",
        "訪問看護": "visit_nursing",
        "自院外来・施設転換": "other",
    }
    quotas = {k: 0.0 for k in CHANNELS}
    for item in playbook:
        key = label_to_key.get(item["channel"], "other")
        quotas[key] = quotas.get(key, 0.0) + float(item.get("share", 0)) * monthly_new_needed
    return {k: round(v, 2) for k, v in quotas.items()}


def resolve_referral(
    clinic_name: str,
    alias: str,
    *,
    monthly_new_needed: Optional[float],
    playbook: List[Dict[str, Any]],
    funnel: Optional[Dict[str, dict]] = None,
) -> ReferralActuals:
    funnel = funnel if funnel is not None else load_referral_funnel()
    if clinic_name in funnel:
        row = funnel[clinic_name]
        by = row["by_channel"]
        total = sum(by.values())
        if total <= 0:
            # 全ゼロは未入力扱い → 推定へフォールスルー
            pass
        else:
            months = row["window_months"]
            notes = [f"実績窓 {months}ヶ月・新規居宅合計 {total}"]
            monthly = total / months if months else 0.0
            if monthly_new_needed and monthly_new_needed > 0:
                notes.append(
                    f"実績月次 {monthly:.1f} vs 必要月次 {monthly_new_needed:.1f}"
                    + ("（不足）" if monthly < monthly_new_needed else "（充足）")
                )
            return ReferralActuals(
                clinic=clinic_name,
                alias=alias,
                window_months=months,
                by_channel=by,
                total_new_home=total,
                source="actual",
                notes=notes,
            )

    needed = float(monthly_new_needed or 0.0)
    quotas = allocate_channel_quotas(needed, playbook)
    # store as int-ish monthly targets in by_channel for planning
    by = {k: int(round(v)) for k, v in quotas.items()}
    return ReferralActuals(
        clinic=clinic_name,
        alias=alias,
        window_months=1,
        by_channel=by,
        total_new_home=sum(by.values()),
        source="estimated",
        notes=[
            "紹介実績未登録のためプレイブック比率で月次割当",
            f"必要月次新規 {needed:.1f} → " + ", ".join(
                f"{CHANNEL_LABELS[k]} {v}" for k, v in by.items() if v
            ),
        ],
    )
