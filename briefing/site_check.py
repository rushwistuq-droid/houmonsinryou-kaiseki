#!/usr/bin/env python3
"""任意の出店候補地を評価する（機密データ不要）。

    python3 briefing/site_check.py --lat 35.8906 --lon 139.7906 --name 越谷駅前
    python3 briefing/site_check.py --address 埼玉県越谷市越ヶ谷1-1    # 国土地理院で住所→座標（要ネット）
    python3 briefing/site_check.py --compare 越谷:35.8906,139.7906 柏:35.8622,139.9707

予測モデルの係数は briefing/output/growth_model.json（build_all.py が出力）を使う。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing.wakasa_brief.engine import Engine  # noqa: E402
from briefing.wakasa_brief.model import GrowthModel  # noqa: E402
from briefing.wakasa_brief.site_score import SiteScorer  # noqa: E402

MODEL_JSON = ROOT / "briefing/output/growth_model.json"


def load_model() -> tuple[GrowthModel, float, float]:
    m = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    c = m["coef"]
    model = GrowthModel(
        coef=np.array([c["a"], c["b_months"], c["c_underserved"], c["d_facility_era"]]),
        r2=m["r2"],
        loo_rmse_log=float(np.log(1 + m["loo_error_pct"] / 100)),
        n=m["n"],
        underserved_range=tuple(m["underserved_range"]),
    )
    return model, m["benchmark_penetration"], m["benchmark_competition_density"]


def geocode(address: str) -> tuple[float, float]:
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(address)
    with urllib.request.urlopen(url, timeout=20) as r:
        hits = json.loads(r.read().decode("utf-8"))
    if not hits:
        raise SystemExit(f"住所が見つかりません: {address}")
    lon, lat = hits[0]["geometry"]["coordinates"]
    return float(lat), float(lon)


def report(name: str, r: dict, model: GrowthModel) -> str:
    lines = [
        f"■ {name}（{r['lat']:.4f}, {r['lon']:.4f}）半径{r['radius_km']:g}km",
        f"  65歳以上 {r['elderly_65']:,.0f}人 / 75歳以上 {r['elderly_75']:,.0f}人（75歳以上の伸び 2020→25: {r['e75_growth_20_25']:.2f}倍）",
        f"  居宅需要（顕在） {r['market_home']:,.0f}人 / 潜在（東京並み） {r['latent_home']:,.0f}人 → 未充足度 {r['underserved_ratio']:.2f}",
        f"  入居系施設 {r['facility_count']}か所・入居者推計 {r['facility_residents']:,.0f}人",
        f"  競合: 在支診・在支病 約{r['competitors_n']:.0f}件（うち機能強化型 約{r['competitors_enhanced_n']:.0f}）"
        f" → 実効競合 {r['competitor_units']:.0f}ユニット、75歳以上1万人あたり {r['competition_density']:.2f}",
        f"  既存院との重複: 新院が最寄りになる高齢者の割合 {r['exclusive_ratio_new']:.0%}"
        f"（最寄り既存院 {r['nearest_clinic']} {r['nearest_clinic_km']:.1f}km）",
        f"  ▶ 3年後の居宅患者予測 {r['pred_home_36m']:,.0f}人（誤差の目安 ±{model.loo_pct:.0%}）"
        f" / うちグループ純増 {r['pred_home_36m_group_net']:,.0f}人",
        f"  ▶ 到達目安 {r['reach_target']:,.0f}人（本院並みの浸透 × 競合補正）",
    ]
    if r["underserved_extrapolated"]:
        lines.append(f"  ※未充足度が既存院の実績範囲（最大{model.underserved_range[1]:.1f}）を超えるため、予測は上限値で頭打ち")
    if r["elderly_65"] < 30_000:
        lines.append("  ※8km圏の高齢者が少なく、モデルの適用範囲外の可能性")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="出店候補地の評価")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--address")
    ap.add_argument("--name", default="候補地")
    ap.add_argument("--radius", type=float, default=8.0)
    ap.add_argument("--compare", nargs="+", metavar="名前:緯度,経度")
    args = ap.parse_args()

    model, bp, bc = load_model()
    scorer = SiteScorer(Engine(), model, bp, bc)
    targets = []
    if args.compare:
        for item in args.compare:
            nm, ll = item.split(":")
            la, lo = map(float, ll.split(","))
            targets.append((nm, la, lo))
    elif args.address:
        la, lo = geocode(args.address)
        targets.append((args.name if args.name != "候補地" else args.address, la, lo))
    elif args.lat is not None and args.lon is not None:
        targets.append((args.name, args.lat, args.lon))
    else:
        ap.error("--lat/--lon、--address、--compare のいずれかを指定してください")
    for nm, la, lo in targets:
        r = scorer.evaluate(la, lo, args.radius)
        print(report(nm, r, model) if r else f"■ {nm}: 圏内に人口データがありません")
        print()


if __name__ == "__main__":
    main()
