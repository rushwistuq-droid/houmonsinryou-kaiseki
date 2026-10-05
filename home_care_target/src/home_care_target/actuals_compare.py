"""実績と実務KPI・公平シェア・居宅ミックスの差分。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pipeline import analyze_all_wakasa
from .wakasa_demo_data import CLINIC_ALIASES

DEFAULT_ACTUALS = (
    Path(__file__).resolve().parents[3]
    / "analysis"
    / "confidential"
    / "wakasa_patient_actuals.yaml"
)


@dataclass
class ActualVsKpiRow:
    clinic: str
    alias: str
    actual_facility: int
    actual_home: int
    actual_total: int
    actual_home_share: float
    fair_share_kpi: int
    operational_kpi: int
    operational_stretch: int
    growth_mode: str
    home_mix_band: Optional[str]
    home_shift_gap: Optional[int]
    gap_vs_operational: int
    attainment_vs_operational: float
    competition_label: str
    ignore_for_priority: bool
    status: str
    physician_fte: Optional[float]


def _parse_simple_actuals_yaml(text: str) -> dict:
    clinics: List[dict] = []
    current: Optional[dict] = None
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
            current = {"alias": line.split(":", 1)[1].strip()}
            continue
        if current is None:
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
            continue
        if ":" in line:
            k, v = line.strip().split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("facility", "home"):
                current[k] = int(v)
            else:
                current[k] = v
    if current:
        clinics.append(current)
    return meta


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _parse_simple_actuals_yaml(text)


def load_actuals(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or DEFAULT_ACTUALS
    if not path.exists():
        raise FileNotFoundError(f"actuals not found: {path}")
    raw = _load_yaml(path)
    out: Dict[str, dict] = {}
    for row in raw.get("clinics", []):
        alias = str(row["alias"])
        full = CLINIC_ALIASES.get(alias, alias)
        out[full] = {
            "alias": alias,
            "facility": int(row["facility"]),
            "home": int(row["home"]),
        }
    return out


def compare_actuals_to_kpi(
    actuals_path: Optional[Path] = None,
    *,
    prefer_points: bool = True,
) -> List[ActualVsKpiRow]:
    actuals = load_actuals(actuals_path)
    rows: List[ActualVsKpiRow] = []
    for a in analyze_all_wakasa(prefer_points=prefer_points, actuals=actuals):
        if a.clinic not in actuals:
            continue
        act = actuals[a.clinic]
        home = act["home"]
        fac = act["facility"]
        total = home + fac
        g = a.growth
        op = a.operational_kpi_home
        if g and g.ignore_for_priority:
            status = "開院初期（優先対象外）"
        elif g and g.home_mix and g.home_mix.band == "施設偏重" and g.home_mix.shift_gap_to_target > 0:
            status = "居宅シフト要"
        elif home >= (g.operational_stretch_home if g else op):
            status = "伸長以上"
        elif home >= op:
            status = "実務KPI達成"
        else:
            status = "実務KPI未達"

        rows.append(
            ActualVsKpiRow(
                clinic=a.clinic,
                alias=act["alias"],
                actual_facility=fac,
                actual_home=home,
                actual_total=total,
                actual_home_share=round(home / total, 3) if total else 0.0,
                fair_share_kpi=a.kpi_target_home,
                operational_kpi=op,
                operational_stretch=g.operational_stretch_home if g else a.acquisition.acquisition_stretch_home,
                growth_mode=g.mode if g else "early",
                home_mix_band=g.home_mix.band if g and g.home_mix else None,
                home_shift_gap=g.home_mix.shift_gap_to_target if g and g.home_mix else None,
                gap_vs_operational=home - op,
                attainment_vs_operational=round(home / op, 3) if op else 0.0,
                competition_label=a.acquisition.competition_label,
                ignore_for_priority=bool(g.ignore_for_priority) if g else False,
                status=status,
                physician_fte=a.physician_fte,
            )
        )
    return rows


def rows_to_public_summary(rows: List[ActualVsKpiRow]) -> dict:
    bands = {
        "開院初期（優先対象外）": 0,
        "居宅シフト要": 0,
        "実務KPI未達": 0,
        "実務KPI達成": 0,
        "伸長以上": 0,
    }
    clinics = []
    for r in rows:
        bands[r.status] = bands.get(r.status, 0) + 1
        clinics.append(
            {
                "clinic": r.clinic,
                "status": r.status,
                "operational_kpi": r.operational_kpi,
                "fair_share_kpi": r.fair_share_kpi,
                "growth_mode": r.growth_mode,
                "home_mix_band": r.home_mix_band,
                "home_shift_gap": r.home_shift_gap,
                "ignore_for_priority": r.ignore_for_priority,
                "gap_vs_operational_sign": (
                    "over" if r.gap_vs_operational > 0 else "at" if r.gap_vs_operational == 0 else "under"
                ),
                "competition_label": r.competition_label,
            }
        )
    return {
        "metric": "home_patients_vs_operational_kpi",
        "n_clinics": len(rows),
        "band_counts": bands,
        "clinics": clinics,
    }


def write_confidential_report(rows: List[ActualVsKpiRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"rows": [asdict(r) for r in rows]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
