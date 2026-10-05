#!/usr/bin/env python3
"""実績 vs 実務KPI 比較を実行する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "home_visit_demand" / "src"))

from home_care_target.actuals_compare import (  # noqa: E402
    compare_actuals_to_kpi,
    rows_to_public_summary,
    write_confidential_report,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Compare actual patients to operational KPI")
    p.add_argument(
        "--actuals",
        type=Path,
        default=Path(os.environ.get("ACTUALS_PATH", "analysis/confidential/wakasa_patient_actuals.yaml")),
    )
    p.add_argument(
        "--confidential-out",
        type=Path,
        default=Path("analysis/confidential/actuals_vs_acquisition.json"),
    )
    p.add_argument(
        "--public-out",
        type=Path,
        default=Path("home_care_target/data/processed/actuals_vs_acquisition_public.json"),
    )
    args = p.parse_args()

    rows = compare_actuals_to_kpi(args.actuals)
    write_confidential_report(rows, args.confidential_out)
    public = rows_to_public_summary(rows)
    args.public_out.parent.mkdir(parents=True, exist_ok=True)
    args.public_out.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'院':<12} {'実績':>6} {'実務KPI':>7} {'差':>6} {'帯':<8} {'状態'}")
    for r in rows:
        print(
            f"{r.alias:<12} {r.actual_home:>6} {r.operational_kpi:>7} "
            f"{r.gap_vs_operational:>+6} {(r.home_mix_band or '-'):<8} {r.status}"
        )
    print(f"\nconfidential -> {args.confidential_out}")
    print(f"public summary -> {args.public_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
