#!/usr/bin/env python3
"""実績YAMLからキャリブレーション係数を計算する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

from home_visit_demand.precision import (  # noqa: E402
    compute_calibration_from_actuals,
    estimate_precision_from_address,
)


def main() -> int:
    p = argparse.ArgumentParser(description="実績データからキャリブレーション係数を算出")
    p.add_argument(
        "actuals",
        type=Path,
        help="calibration.yaml（clinics[].actual_home_patients を含む）",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "calibration.yaml",
    )
    p.add_argument("--radius-km", type=float, default=8.0)
    p.add_argument("--shrink", type=float, default=0.3, help="全国寄り縮小係数")
    args = p.parse_args()

    data = yaml.safe_load(args.actuals.read_text(encoding="utf-8"))
    clinics = data.get("clinics") or []
    if not clinics:
        print("clinics が空です", file=sys.stderr)
        return 1

    model_homes = []
    enriched = []
    for c in clinics:
        lat, lon = c.get("lat"), c.get("lon")
        res = estimate_precision_from_address(
            c["address"],
            radius_km=args.radius_km,
            lat=lat,
            lon=lon,
            clinic_id=c.get("id"),
        )
        model_homes.append(res.recommended_home_patients)
        ratio = None
        if c.get("actual_home_patients") and res.recommended_home_patients:
            ratio = c["actual_home_patients"] / res.recommended_home_patients
        enriched.append({
            **c,
            "model_home_patients": res.recommended_home_patients,
            "model_total_patients": res.visit_patients_total,
            "ratio_actual_over_model": None if ratio is None else round(ratio, 3),
            "calibration_factor": None if ratio is None else round(ratio, 3),
        })
        print(
            f"{c.get('id') or c.get('name')}: actual={c.get('actual_home_patients')} "
            f"model={res.recommended_home_patients:.1f} ratio={ratio}"
        )

    global_factor = compute_calibration_from_actuals(clinics, model_homes, shrink=args.shrink)
    out = {
        "meta": {
            **(data.get("meta") or {}),
            "shrink": args.shrink,
            "radius_km": args.radius_km,
        },
        "global_calibration_factor": round(global_factor, 3),
        "clinics": enriched,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"global_calibration_factor={global_factor:.3f} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
