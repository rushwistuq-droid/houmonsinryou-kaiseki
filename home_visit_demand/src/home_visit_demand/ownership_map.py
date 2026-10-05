"""グループ院のメッシュ主担当（最寄り院）マップ生成。"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from typing import Any

from .estimator import haversine_km
from .hq_analysis import ClinicInput, patients_from_mesh_bands, recommended_home_from_raw
from .precision import _load_mesh, mesh_intersection_weight, scale_mesh_to_2025


MITAKA_CLUSTER_IDS = (
    "shakujii",
    "hibarigaoka",
    "mitaka",
    "chofu",
    "fuchu",
    "koenji",
)


@dataclass
class OwnershipCell:
    mesh_code: str
    lat: float
    lon: float
    elderly_65: float
    owner_id: str
    owner_name: str
    cover_count: int


@dataclass
class OwnershipSummary:
    radius_km: float
    clinic_ids: list[str]
    exclusive_elderly: dict[str, float]
    exclusive_home_market: dict[str, float]
    contested_elderly: float
    cells_sample: list[dict[str, Any]]
    bounds: dict[str, float]


def build_mesh_ownership(
    clinics: list[ClinicInput],
    radius_km: float = 8.0,
) -> tuple[OwnershipSummary, list[OwnershipCell]]:
    df = _load_mesh()
    # mesh_code -> meta + coverers
    index: dict[str, dict[str, Any]] = {}
    id_to_name = {c.id: c.name for c in clinics}

    for c in clinics:
        ddeg = (radius_km + 1.0) / 80.0
        sub = df[
            (df["lat"] >= c.lat - ddeg)
            & (df["lat"] <= c.lat + ddeg)
            & (df["lon"] >= c.lon - ddeg)
            & (df["lon"] <= c.lon + ddeg)
        ]
        for r in sub.itertuples(index=False):
            d = haversine_km(c.lat, c.lon, float(r.lat), float(r.lon))
            w = mesh_intersection_weight(d, radius_km)
            if w <= 0:
                continue
            code = str(r.mesh_code)
            if code not in index:
                index[code] = {
                    "lat": float(r.lat),
                    "lon": float(r.lon),
                    "pref_code": str(r.pref_code).zfill(2),
                    "elderly_65": float(r.elderly_65),
                    "elderly_75": float(r.elderly_75),
                    "elderly_85": float(r.elderly_85),
                    "elderly_95": float(r.elderly_95),
                    "coverers": [],
                }
            index[code]["coverers"].append((c.id, d, w))

    cells: list[OwnershipCell] = []
    exclusive_raw: dict[str, dict[str, float]] = {
        c.id: {"e65": 0.0, "e75": 0.0, "e85": 0.0, "e95": 0.0, "pref_w": {}}
        for c in clinics
    }
    contested = 0.0
    lats, lons = [], []

    for code, meta in index.items():
        coverers = meta["coverers"]
        max_w = max(w for _, _, w in coverers)
        e65 = meta["elderly_65"] * max_w
        owner_id = min(coverers, key=lambda t: (t[1], t[0]))[0]
        if len(coverers) >= 2:
            contested += e65
        er = exclusive_raw[owner_id]
        er["e65"] += e65
        er["e75"] += meta["elderly_75"] * max_w
        er["e85"] += meta["elderly_85"] * max_w
        er["e95"] += meta["elderly_95"] * max_w
        pw = er["pref_w"]
        pw[meta["pref_code"]] = pw.get(meta["pref_code"], 0.0) + e65
        cells.append(
            OwnershipCell(
                mesh_code=code,
                lat=meta["lat"],
                lon=meta["lon"],
                elderly_65=e65,
                owner_id=owner_id,
                owner_name=id_to_name.get(owner_id, owner_id),
                cover_count=len(coverers),
            )
        )
        lats.append(meta["lat"])
        lons.append(meta["lon"])

    exclusive_elderly = {}
    exclusive_home = {}
    for c in clinics:
        er = exclusive_raw[c.id]
        prefs = sorted(er["pref_w"].keys()) or ["13"]
        bands = scale_mesh_to_2025(er["e65"], er["e75"], er["e85"], er["e95"], prefs)
        pref = max(er["pref_w"], key=er["pref_w"].get) if er["pref_w"] else "13"
        tot, hm, fc = patients_from_mesh_bands(bands, pref)
        rec, _ = recommended_home_from_raw(tot, hm, fc, 0.0, sum(bands.values()))
        exclusive_elderly[c.id] = round(sum(bands.values()), 1)
        exclusive_home[c.id] = round(rec, 1)

    # growth for contested
    growth = 1.0
    if exclusive_raw:
        raw_sum = sum(v["e65"] for v in exclusive_raw.values())
        scaled = sum(exclusive_elderly.values())
        growth = scaled / raw_sum if raw_sum else 1.0

    summary = OwnershipSummary(
        radius_km=radius_km,
        clinic_ids=[c.id for c in clinics],
        exclusive_elderly=exclusive_elderly,
        exclusive_home_market=exclusive_home,
        contested_elderly=round(contested * growth, 1),
        cells_sample=[asdict(c) for c in cells[:5]],
        bounds={
            "lat_min": min(lats) if lats else 0,
            "lat_max": max(lats) if lats else 0,
            "lon_min": min(lons) if lons else 0,
            "lon_max": max(lons) if lons else 0,
        },
    )
    return summary, cells


def render_ownership_map_html(
    clinics: list[ClinicInput],
    summary: OwnershipSummary,
    cells: list[OwnershipCell],
    *,
    title: str = "メッシュ主担当マップ",
) -> str:
    """Leaflet不要の簡易キャンバス地図（相対配置）。"""
    colors = [
        "#0f5c4c",
        "#8a3b12",
        "#1f4f8f",
        "#6b2d5c",
        "#3d6b1f",
        "#7a5a10",
        "#4a4a4a",
        "#0b6e4f",
    ]
    id_color = {cid: colors[i % len(colors)] for i, cid in enumerate(summary.clinic_ids)}
    b = summary.bounds
    # downsample for HTML size: keep high-elderly and contested preferentially
    cells_sorted = sorted(cells, key=lambda c: (-c.cover_count, -c.elderly_65))
    plot = cells_sorted[:8000]

    def xy(lat, lon):
        # simple equirectangular into 900x700
        x = (lon - b["lon_min"]) / max(b["lon_max"] - b["lon_min"], 1e-6) * 900
        y = (b["lat_max"] - lat) / max(b["lat_max"] - b["lat_min"], 1e-6) * 700
        return x, y

    dots = []
    for c in plot:
        x, y = xy(c.lat, c.lon)
        col = id_color.get(c.owner_id, "#333")
        r = 1.6 if c.cover_count == 1 else 2.4
        opacity = 0.55 if c.cover_count == 1 else 0.85
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}" fill-opacity="{opacity}">'
            f'<title>{html.escape(c.owner_name)} / 65+={c.elderly_65:.0f} / カバー{c.cover_count}</title></circle>'
        )

    clinic_marks = []
    legend = []
    for i, c in enumerate(clinics):
        x, y = xy(c.lat, c.lon)
        col = id_color[c.id]
        clinic_marks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#fff" stroke="{col}" stroke-width="3"/>'
            f'<text x="{x+8:.1f}" y="{y+4:.1f}" font-size="12" fill="#1c2430">{html.escape(c.name)}</text>'
        )
        legend.append(
            f'<div class="leg"><span style="background:{col}"></span>'
            f'{html.escape(c.name)}　排他65+ {summary.exclusive_elderly.get(c.id,0):,.0f}　'
            f'排他居宅≈{summary.exclusive_home_market.get(c.id,0):,.0f}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
body{{margin:0;font-family:"IBM Plex Sans JP","Hiragino Sans",sans-serif;background:#f3f0e8;color:#1c2430}}
header{{padding:1.4rem 1.2rem;border-bottom:1px solid #d5d0c4;background:#fffdf8}}
h1{{margin:0;font-family:"Shippori Mincho","Yu Mincho",serif;color:#0f5c4c;font-size:1.5rem}}
p{{color:#5b6573;margin:.4rem 0 0}}
main{{display:grid;grid-template-columns:1fr 280px;gap:1rem;padding:1rem}}
svg{{width:100%;height:auto;background:#fffdf8;border:1px solid #d5d0c4;border-radius:12px}}
.leg{{display:flex;gap:.5rem;align-items:center;margin:.35rem 0;font-size:.9rem}}
.leg span{{width:14px;height:14px;border-radius:3px;display:inline-block}}
.note{{font-size:.85rem;color:#5b6573}}
@media(max-width:900px){{main{{grid-template-columns:1fr}}}}
</style></head><body>
<header>
<h1>{html.escape(title)}</h1>
<p>各メッシュを最寄りグループ院に割り当て（半径{summary.radius_km:g}km）。色=主担当、濃い点=複数院カバー（係争）。</p>
</header>
<main>
<svg viewBox="0 0 900 700" role="img" aria-label="ownership map">
{''.join(dots)}
{''.join(clinic_marks)}
</svg>
<aside>
<h2>凡例・排他的市場</h2>
{''.join(legend)}
<p class="note">係争メッシュ高齢者（概算）: {summary.contested_elderly:,.0f}<br/>
表示メッシュ: {len(plot):,} / 全{len(cells):,}（高齢・係争優先で間引き）</p>
<p class="note">運用: 居宅の一次受付は主担当院優先。係争点は施設契約と役割表で調整。</p>
</aside>
</main>
</body></html>
"""


def write_cluster_ownership_map(
    clinics: list[ClinicInput],
    out_path,
    *,
    radius_km: float = 8.0,
    title: str = "三鷹クラスター メッシュ主担当マップ",
) -> OwnershipSummary:
    from pathlib import Path

    summary, cells = build_mesh_ownership(clinics, radius_km=radius_km)
    html_text = render_ownership_map_html(clinics, summary, cells, title=title)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    # also json summary
    side = path.with_suffix(".json")
    side.write_text(
        json.dumps(
            {
                "radius_km": summary.radius_km,
                "exclusive_elderly": summary.exclusive_elderly,
                "exclusive_home_market": summary.exclusive_home_market,
                "contested_elderly": summary.contested_elderly,
                "clinic_ids": summary.clinic_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary
