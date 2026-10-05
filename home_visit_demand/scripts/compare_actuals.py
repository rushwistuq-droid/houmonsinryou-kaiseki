#!/usr/bin/env python3
"""実績と高精度推計を突合し、本部向け比較レポートを出力する。"""

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
    p = argparse.ArgumentParser()
    p.add_argument(
        "actuals",
        type=Path,
        default=ROOT / "data" / "confidential" / "actuals_2026-07.yaml",
        nargs="?",
    )
    p.add_argument("--radius-km", type=float, default=8.0)
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "examples" / "wakasa_actual_vs_model_report.txt",
    )
    p.add_argument(
        "--calibration-out",
        type=Path,
        default=ROOT / "data" / "processed" / "calibration.yaml",
    )
    args = p.parse_args()

    data = yaml.safe_load(args.actuals.read_text(encoding="utf-8"))
    clinics = data["clinics"]

    rows = []
    for c in clinics:
        print(f"estimating {c['name']}...", flush=True)
        r = estimate_precision_from_address(
            c["address"],
            radius_km=args.radius_km,
            lat=c.get("lat"),
            lon=c.get("lon"),
            clinic_id=c.get("id"),
        )
        actual_home = float(c["actual_home_patients"])
        actual_fac = float(c["actual_facility_patients"])
        actual_total = actual_home + actual_fac
        model_home = r.recommended_home_patients
        model_fac = r.visit_patients_facility_true
        model_total = r.visit_patients_total
        home_ratio = (actual_home / model_home) if model_home else None
        # 市場シェア（推計需要に対する実績）
        home_share = (100.0 * actual_home / model_home) if model_home else None
        total_share = (100.0 * actual_total / model_total) if model_total else None
        rows.append({
            "id": c["id"],
            "name": c["name"],
            "actual_home": actual_home,
            "actual_fac": actual_fac,
            "actual_total": actual_total,
            "model_home": model_home,
            "model_fac": model_fac,
            "model_total": model_total,
            "home_ratio": home_ratio,
            "home_share_pct": home_share,
            "total_share_pct": total_share,
            "elderly_65": r.demographics["elderly_65"],
            "facility_residents": r.facility_summary["residents_est"],
            "pref": r.pref_intensity["pref_name"],
            "home_intensity": r.pref_intensity.get("home_intensity_vs_national"),
            "mesh_count": r.mesh_count,
        })

    # キャリブレーション（居宅）: 開院間もない浦和は除外して係数算出も検討
    calib_clinics = [c for c in clinics if c["id"] != "urawa"]
    calib_models = [r["model_home"] for r in rows if r["id"] != "urawa"]
    global_factor = compute_calibration_from_actuals(
        calib_clinics, calib_models, shrink=0.25
    )

    # 院別係数
    for row, c in zip(rows, clinics):
        if row["home_ratio"] is not None:
            c["model_home_patients"] = row["model_home"]
            c["model_facility_patients"] = row["model_fac"]
            c["model_total_patients"] = row["model_total"]
            c["ratio_actual_over_model"] = round(row["home_ratio"], 3)
            c["calibration_factor"] = round(row["home_ratio"], 3)
            c["home_market_share_pct"] = round(row["home_share_pct"], 2)
            c["total_market_share_pct"] = round(row["total_share_pct"], 2)

    calib_out = {
        "meta": {
            **(data.get("meta") or {}),
            "radius_km": args.radius_km,
            "shrink": 0.25,
            "note": "浦和は開院直後のため global 係数算出から除外",
        },
        "global_calibration_factor": round(global_factor, 3),
        "clinics": clinics,
    }
    args.calibration_out.parent.mkdir(parents=True, exist_ok=True)
    args.calibration_out.write_text(
        yaml.safe_dump(calib_out, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # レポート
    lines = []
    lines.append("=" * 96)
    lines.append("わかさクリニックグループ 実績 vs 地域推計 突合レポート（本部検証用）")
    lines.append("=" * 96)
    lines.append(f"推計半径: {args.radius_km:g} km / 手法: メッシュ人口×都道府県別NDB×施設実在")
    lines.append(f"実績基準: {data.get('meta', {}).get('as_of', '')}")
    lines.append(
        f"参考・自院居宅÷市場推計の縮小平均（浦和除外・shrink=0.25）: {global_factor:.3f}"
    )
    lines.append("※上記は市場規模の補正ではなく、自院獲得率の参考値。市場推計自体は未補正のまま。")
    lines.append("")
    lines.append("【実績構成（施設 / 居宅）】")
    lines.append(
        f"{'院名':<8} {'実績施設':>8} {'実績居宅':>8} {'合計':>8} {'施設比率%':>8} {'居宅比率%':>8}"
    )
    lines.append("-" * 64)
    for r in rows:
        fac_pct = 100.0 * r["actual_fac"] / r["actual_total"] if r["actual_total"] else 0.0
        home_pct = 100.0 * r["actual_home"] / r["actual_total"] if r["actual_total"] else 0.0
        lines.append(
            f"{r['name']:<8} {r['actual_fac']:>8.0f} {r['actual_home']:>8.0f} "
            f"{r['actual_total']:>8.0f} {fac_pct:>8.1f} {home_pct:>8.1f}"
        )
    lines.append("")
    lines.append("【実績 vs 地域市場推計】")
    lines.append(
        f"{'院名':<8} {'実績居宅':>8} {'推計居宅':>8} {'実績/推計':>8} "
        f"{'居宅ｼｪｱ%':>8} {'実績施設':>8} {'推計施設':>8} {'実績合計':>8} {'合計ｼｪｱ%':>8}"
    )
    lines.append("-" * 96)
    for r in rows:
        ratio_s = f"{r['home_ratio']:.2f}" if r["home_ratio"] is not None else "-"
        hs = f"{r['home_share_pct']:.1f}" if r["home_share_pct"] is not None else "-"
        ts = f"{r['total_share_pct']:.1f}" if r["total_share_pct"] is not None else "-"
        lines.append(
            f"{r['name']:<8} {r['actual_home']:>8.0f} {r['model_home']:>8.1f} {ratio_s:>8} "
            f"{hs:>8} {r['actual_fac']:>8.0f} {r['model_fac']:>8.1f} "
            f"{r['actual_total']:>8.0f} {ts:>8}"
        )
    lines.append("-" * 96)
    sum_ah = sum(r["actual_home"] for r in rows)
    sum_mh = sum(r["model_home"] for r in rows)
    sum_af = sum(r["actual_fac"] for r in rows)
    sum_at = sum(r["actual_total"] for r in rows)
    lines.append(
        f"{'合計':<8} {sum_ah:>8.0f} {sum_mh:>8.1f} {sum_ah/sum_mh:>8.2f} "
        f"{100*sum_ah/sum_mh:>8.1f} {sum_af:>8.0f} {'':>8} {sum_at:>8.0f}"
    )
    lines.append("")
    lines.append("【読み方】")
    lines.append("  - 推計居宅 = 半径8kmの地域に発生しうる居宅訪問診療患者数（市場規模）")
    lines.append("  - 実績/推計・居宅シェア% = 自院居宅患者 ÷ 地域市場推計（獲得率の近似）")
    lines.append("  - 東京圏は高齢者密度が高く市場推計が大きいため、シェアは数%でも競合下では妥当な水準になりうる")
    lines.append("  - 推計施設 = 圏内施設需要。実績施設は契約施設中心のためシェアは参考値")
    lines.append("  - 浦和は開院直後のためシェア解釈は慎重に")
    lines.append("  - 市川など県境院は、圏内高齢者の主たる都道府県名が表示される（受療率適用のため）")
    lines.append("")
    lines.append("【院別コメント（構造要因）】")
    # 簡易コメント
    for r in rows:
        note = []
        if r["id"] == "urawa":
            note.append("開院直後・実績僅少")
        if r["home_share_pct"] is not None:
            if r["home_share_pct"] >= 20:
                note.append("居宅シェア高（強い獲得）")
            elif r["home_share_pct"] >= 7:
                note.append("居宅シェア中〜高")
            elif r["home_share_pct"] <= 3:
                note.append("居宅シェア低（競合密・居宅比重の差）")
        if r["actual_fac"] > r["actual_home"] * 2:
            note.append("施設偏重")
        elif r["actual_home"] > r["actual_fac"]:
            note.append("居宅優勢")
        lines.append(
            f"  - {r['name']}: 圏域主県={r['pref']} / 65+={r['elderly_65']:,.0f} / "
            + (" / ".join(note) if note else "標準")
        )
    lines.append("")
    lines.append("【キャリブレーション】")
    lines.append(f"  出力: {args.calibration_out}（gitignore・機密）")
    lines.append("  院別 ratio は自院獲得率。市場規模推計には掛けないこと。")
    lines.append("=" * 96)

    text = "\n".join(lines)
    print(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
