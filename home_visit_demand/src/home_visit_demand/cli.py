#!/usr/bin/env python3
"""クリニック住所から半径圏内の居宅訪問診療患者数を推定するCLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.estimator import (  # noqa: E402
    estimate_from_address,
    format_report,
)
from home_visit_demand.precision import (  # noqa: E402
    estimate_precision_from_address,
    format_precision_report,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="クリニック住所から半径N kmの訪問診療・居宅患者数を推定します。"
    )
    p.add_argument("address", help="クリニックの住所（例: 埼玉県所沢市若狭4-2468-31）")
    p.add_argument("--radius-km", type=float, default=8.0, help="集計半径km（既定: 8）")
    p.add_argument("--lat", type=float, default=None, help="緯度（指定時はジオコード省略）")
    p.add_argument("--lon", type=float, default=None, help="経度（指定時はジオコード省略）")
    p.add_argument(
        "--facility-beds",
        type=float,
        default=None,
        help="圏内の入所定員が分かる場合に指定（v1互換）",
    )
    p.add_argument(
        "--precision",
        action="store_true",
        default=True,
        help="高精度モード（メッシュ×都道府県受療率×施設実在）既定ON",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="旧ロジック（市区町村代表点）を使用",
    )
    p.add_argument("--clinic-id", default=None, help="キャリブレーション用ID")
    p.add_argument("--calibration-factor", type=float, default=None)
    p.add_argument("--json", action="store_true", help="JSONで出力")
    p.add_argument("-o", "--output", type=Path, default=None, help="結果ファイル出力先")
    args = p.parse_args(argv)

    use_precision = args.precision and not args.legacy
    if use_precision:
        result = estimate_precision_from_address(
            args.address,
            radius_km=args.radius_km,
            lat=args.lat,
            lon=args.lon,
            clinic_id=args.clinic_id,
            calibration_factor=args.calibration_factor,
        )
        text = (
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            if args.json
            else format_precision_report(result)
        )
    else:
        result = estimate_from_address(
            args.address,
            radius_km=args.radius_km,
            lat=args.lat,
            lon=args.lon,
            facility_beds_override=args.facility_beds,
        )
        text = (
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            if args.json
            else format_report(result)
        )

    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
