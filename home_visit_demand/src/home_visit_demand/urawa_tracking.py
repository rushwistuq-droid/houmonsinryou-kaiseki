"""浦和院の立ち上がりトラッキング（3/6/12か月）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hq_analysis import ClinicInput, build_clinic_market_row

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass
class RampPoint:
    month: str  # YYYY-MM
    actual_home: float
    actual_facility: float
    market_home_8km: float
    market_home_5km: float
    capture_8km_pct: float | None
    capture_5km_pct: float | None
    exclusive_home_market: float | None = None
    notes: str = ""


def default_urawa_clinic() -> ClinicInput:
    return ClinicInput(
        id="urawa",
        name="浦和",
        lat=35.880526,
        lon=139.641896,
        address="埼玉県さいたま市浦和区針ヶ谷1-2-11",
        actual_home_patients=14,
        actual_facility_patients=0,
    )


def load_ramp_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise ImportError("pyyaml required")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_urawa_tracking(
    ramp_data: dict[str, Any],
    *,
    clinic: ClinicInput | None = None,
) -> list[RampPoint]:
    """月次実績YAMLから獲得率軌跡を計算。市場は最新推計を各月に共通適用。"""
    clinic = clinic or default_urawa_clinic()
    # market once
    row8 = build_clinic_market_row(clinic, [clinic], 8.0)
    row5 = build_clinic_market_row(clinic, [clinic], 5.0)
    m8 = row8.market_home
    m5 = row5.market_home
    # 単院の場合、排他≈圏域市場
    excl = row8.exclusive_market_home or m8

    points: list[RampPoint] = []
    for m in ramp_data.get("months") or []:
        ah = float(m.get("actual_home_patients") or 0)
        af = float(m.get("actual_facility_patients") or 0)
        c8 = 100.0 * ah / m8 if m8 else None
        c5 = 100.0 * ah / m5 if m5 else None
        points.append(
            RampPoint(
                month=str(m["month"]),
                actual_home=ah,
                actual_facility=af,
                market_home_8km=m8,
                market_home_5km=m5,
                capture_8km_pct=round(c8, 2) if c8 is not None else None,
                capture_5km_pct=round(c5, 2) if c5 is not None else None,
                exclusive_home_market=excl,
                notes=str(m.get("notes") or ""),
            )
        )
    return points


def expected_band_for_urawa() -> tuple[float, float]:
    clinic = default_urawa_clinic()
    row = build_clinic_market_row(clinic, [clinic], 8.0)
    return row.expected_share_low_pct, row.expected_share_high_pct


def format_urawa_tracking(points: list[RampPoint], band: tuple[float, float]) -> str:
    low, high = band
    lines = [
        "=" * 88,
        "浦和院 立ち上がりトラッキング（3/6/12か月）",
        "=" * 88,
        f"期待獲得率帯（8km・外部競合込み）: {low:g}–{high:g}%",
        "市場規模は最新推計を各月に共通適用（分母固定で軌跡を見る）。",
        "",
        f"{'月':<10} {'実績居宅':>8} {'実績施設':>8} {'5km獲得%':>8} {'8km獲得%':>8} {'帯判定':>8} {'メモ'}",
        "-" * 88,
    ]
    for p in points:
        c5 = f"{p.capture_5km_pct:.2f}" if p.capture_5km_pct is not None else "-"
        c8 = f"{p.capture_8km_pct:.2f}" if p.capture_8km_pct is not None else "-"
        if p.capture_8km_pct is None:
            judge = "-"
        elif p.capture_8km_pct < low:
            judge = "below"
        elif p.capture_8km_pct > high:
            judge = "above"
        else:
            judge = "within"
        lines.append(
            f"{p.month:<10} {p.actual_home:>8.0f} {p.actual_facility:>8.0f} "
            f"{c5:>8} {c8:>8} {judge:>8} {p.notes}"
        )
    lines.append("-" * 88)
    if points:
        p0, p1 = points[0], points[-1]
        if p0.capture_8km_pct is not None and p1.capture_8km_pct is not None:
            lines.append(
                f"変化: 8km獲得率 {p0.capture_8km_pct:.2f}% → {p1.capture_8km_pct:.2f}% "
                f"（Δ{p1.capture_8km_pct - p0.capture_8km_pct:+.2f}pt）"
            )
        lines.append(
            f"参考: 8km居宅市場={points[-1].market_home_8km:,.0f} / "
            f"5km={points[-1].market_home_5km:,.0f} / "
            f"排他居宅≈{points[-1].exclusive_home_market:,.0f}"
        )
    lines.append("")
    lines.append("【運用】")
    lines.append("  - 開院から3/6/12か月時点を必ず記録（月次実績YAMLを更新）")
    lines.append("  - 短期KPIは5km獲得率と新規居宅件数。8kmは監視指標")
    lines.append("  - 帯到達前に施設偏重へ寄せない")
    lines.append("=" * 88)
    return "\n".join(lines)


def render_urawa_tracking_html(points: list[RampPoint], band: tuple[float, float]) -> str:
    low, high = band
    rows = []
    for p in points:
        c8 = p.capture_8km_pct or 0
        rows.append(
            f"<tr><td>{p.month}</td><td>{p.actual_home:.0f}</td><td>{p.actual_facility:.0f}</td>"
            f"<td>{'-' if p.capture_5km_pct is None else f'{p.capture_5km_pct:.2f}'}</td>"
            f"<td>{'-' if p.capture_8km_pct is None else f'{p.capture_8km_pct:.2f}'}</td>"
            f"<td>{p.notes}</td></tr>"
        )
    # sparkline as SVG bars for 8km capture
    bars = []
    max_c = max((p.capture_8km_pct or 0) for p in points) if points else 1
    max_c = max(max_c, high, 1)
    for i, p in enumerate(points):
        h = ((p.capture_8km_pct or 0) / max_c) * 120
        x = 40 + i * 60
        bars.append(
            f'<rect x="{x}" y="{140-h:.1f}" width="36" height="{h:.1f}" fill="#0f5c4c"/>'
            f'<text x="{x+18}" y="158" text-anchor="middle" font-size="11">{p.month[5:]}</text>'
        )
    band_y = 140 - (high / max_c) * 120
    band_y2 = 140 - (low / max_c) * 120
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"/>
<title>浦和 立ち上がりトラッキング</title>
<style>
body{{margin:0;font-family:"IBM Plex Sans JP","Hiragino Sans",sans-serif;background:#f3f0e8;color:#1c2430}}
header,main{{padding:1.2rem}}
h1{{font-family:"Shippori Mincho","Yu Mincho",serif;color:#0f5c4c}}
table{{border-collapse:collapse;width:100%;background:#fffdf8}}
th,td{{border-bottom:1px solid #d5d0c4;padding:.45rem;text-align:left}}
.note{{color:#5b6573}}
svg{{background:#fffdf8;border:1px solid #d5d0c4;border-radius:12px;width:100%;max-width:520px}}
</style></head><body>
<header>
<h1>浦和院 立ち上がりトラッキング</h1>
<p class="note">期待帯（8km）: {low:g}–{high:g}% ／ 棒=8km獲得率、帯=期待レンジ</p>
</header>
<main>
<svg viewBox="0 0 400 170">
<rect x="30" y="{band_y:.1f}" width="340" height="{max(band_y2-band_y,1):.1f}" fill="#e4efe9"/>
{''.join(bars)}
</svg>
<table>
<thead><tr><th>月</th><th>実績居宅</th><th>実績施設</th><th>5km%</th><th>8km%</th><th>メモ</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</main></body></html>
"""


def write_urawa_tracking(ramp_yaml: Path, out_txt: Path, out_html: Path | None = None) -> list[RampPoint]:
    data = load_ramp_yaml(ramp_yaml)
    points = build_urawa_tracking(data)
    band = expected_band_for_urawa()
    text = format_urawa_tracking(points, band)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(text, encoding="utf-8")
    if out_html:
        out_html.write_text(render_urawa_tracking_html(points, band), encoding="utf-8")
    # json
    out_txt.with_suffix(".json").write_text(
        json.dumps([asdict(p) for p in points], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return points
