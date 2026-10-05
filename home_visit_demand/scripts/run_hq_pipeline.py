#!/usr/bin/env python3
"""本部向けパイプライン: 在支診競合・重複・感度・アクション・主担当マップ・浦和軌跡。"""

from __future__ import annotations

import argparse
import importlib.util
import json
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

from home_visit_demand.action_sheets import (  # noqa: E402
    build_action_sheets,
    format_action_sheets,
)
from home_visit_demand.dashboard import write_hq_dashboard  # noqa: E402
from home_visit_demand.hq_analysis import (  # noqa: E402
    ClinicInput,
    clinics_from_actuals_yaml,
    format_hq_report,
    run_hq_pipeline,
)
from home_visit_demand.ownership_map import (  # noqa: E402
    MITAKA_CLUSTER_IDS,
    write_cluster_ownership_map,
)
from home_visit_demand.precision import DATA_DIR  # noqa: E402
from home_visit_demand.urawa_tracking import write_urawa_tracking  # noqa: E402


def _run_builder(script_name: str) -> None:
    path = ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    mod.build()


def ensure_datasets() -> None:
    if not (
        (DATA_DIR / "competitors_home.csv.gz").exists()
        and (DATA_DIR / "clinics_all_coords.csv.gz").exists()
    ):
        print("building medical-info-net competitors...", flush=True)
        _run_builder("build_competitors.py")
    if not (DATA_DIR / "zaishishin.csv.gz").exists():
        print("building zaishishin from Koseikyoku...", flush=True)
        _run_builder("build_zaishishin.py")


def main() -> int:
    p = argparse.ArgumentParser(description="本部向け地域分析パイプライン")
    p.add_argument(
        "actuals",
        type=Path,
        nargs="?",
        default=ROOT / "data" / "confidential" / "actuals_2026-07.yaml",
    )
    p.add_argument("--radius-km", type=float, default=8.0)
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "examples" / "wakasa_hq_pipeline_report.txt",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=ROOT / "examples" / "wakasa_hq_pipeline.json",
    )
    p.add_argument(
        "--actions-out",
        type=Path,
        default=ROOT / "examples" / "wakasa_action_sheets.txt",
    )
    p.add_argument(
        "--dashboard-out",
        type=Path,
        default=ROOT / "examples" / "wakasa_hq_dashboard.html",
    )
    p.add_argument(
        "--ownership-out",
        type=Path,
        default=ROOT / "examples" / "mitaka_cluster_ownership_map.html",
    )
    p.add_argument(
        "--urawa-out",
        type=Path,
        default=ROOT / "examples" / "urawa_ramp_tracking.txt",
    )
    p.add_argument("--skip-build", action="store_true")
    args = p.parse_args()

    if not args.actuals.exists():
        print(f"actuals not found: {args.actuals}", file=sys.stderr)
        return 1

    if not args.skip_build:
        ensure_datasets()

    data = yaml.safe_load(args.actuals.read_text(encoding="utf-8"))
    clinics = clinics_from_actuals_yaml(data)
    print(f"running HQ pipeline for {len(clinics)} clinics...", flush=True)
    result = run_hq_pipeline(clinics, primary_radius_km=args.radius_km)
    text = format_hq_report(result)
    print(text)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    args.json_out.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    actions = build_action_sheets(result)
    args.actions_out.write_text(format_action_sheets(actions), encoding="utf-8")

    dash = write_hq_dashboard(result, args.dashboard_out)

    # 三鷹クラスター主担当マップ
    by_id = {c.id: c for c in clinics}
    cluster = [
        by_id[i]
        for i in MITAKA_CLUSTER_IDS
        if i in by_id
    ]
    if cluster:
        print(f"writing ownership map for {len(cluster)} cluster clinics...", flush=True)
        write_cluster_ownership_map(
            cluster,
            args.ownership_out,
            radius_km=args.radius_km,
            title="三鷹クラスター メッシュ主担当マップ",
        )

    # 浦和トラッキング
    urawa_yaml = ROOT / "data" / "confidential" / "urawa_ramp.yaml"
    if urawa_yaml.exists():
        print("writing Urawa ramp tracking...", flush=True)
        write_urawa_tracking(
            urawa_yaml,
            args.urawa_out,
            args.urawa_out.with_suffix(".html"),
        )

    print(f"\nwrote {args.output}", flush=True)
    print(f"wrote {args.json_out}", flush=True)
    print(f"wrote {args.actions_out}", flush=True)
    print(f"wrote {dash}", flush=True)
    print(f"wrote {args.ownership_out}", flush=True)
    print(f"wrote {args.urawa_out}", flush=True)
    print(f"rules: {ROOT / 'docs' / 'HQ_OPERATING_RULES.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
