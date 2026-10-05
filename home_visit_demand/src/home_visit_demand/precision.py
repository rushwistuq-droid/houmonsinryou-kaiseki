"""高精度版: メッシュ人口・都道府県受療率・施設実在・同一建物補正。"""

from __future__ import annotations

import gzip
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .estimator import (
    DEFAULT_RADIUS_KM,
    GeoPoint,
    geocode_address,
    haversine_km,
    load_json,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# メッシュ半対角（1/4メッシュ≈250m → 半対角≈177m）
MESH_HALF_DIAG_KM = 0.177


@dataclass
class MeshContribution:
    mesh_code: str
    pref_code: str
    distance_km: float
    weight: float
    pop_total: float
    elderly_65: float
    elderly_75: float
    elderly_85: float
    elderly_95: float


@dataclass
class FacilityHit:
    name: str
    service_name: str
    distance_km: float
    capacity: float
    residents_est: float


@dataclass
class PrecisionEstimationResult:
    address: str
    geocoded_name: str
    lat: float
    lon: float
    radius_km: float
    method: str
    demographics: dict[str, float]
    mesh_count: int
    facility_summary: dict[str, float]
    facilities_top: list[dict]
    age_band_estimates: list[dict]
    visit_patients_total: float
    visit_patients_facility_true: float
    visit_patients_apartment_same_building: float
    visit_patients_home_detached: float
    visit_patients_home_total: float
    recommended_home_patients: float
    recommended_home_patients_calibrated: float | None
    calibration_factor: float | None
    pref_intensity: dict[str, float]
    quality_flags: list[str]
    method_notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_MESH_DF: pd.DataFrame | None = None
_FAC_DF: pd.DataFrame | None = None


def _load_mesh() -> pd.DataFrame:
    global _MESH_DF
    if _MESH_DF is None:
        path = DATA_DIR / "mesh_elderly.csv.gz"
        if not path.exists():
            raise FileNotFoundError(f"{path} がありません。scripts/build_v2_datasets.py を実行してください。")
        _MESH_DF = pd.read_csv(path)
    return _MESH_DF


def _load_facilities() -> pd.DataFrame:
    global _FAC_DF
    if _FAC_DF is None:
        path = DATA_DIR / "facilities.csv.gz"
        if not path.exists():
            raise FileNotFoundError(f"{path} がありません。scripts/build_v2_datasets.py を実行してください。")
        _FAC_DF = pd.read_csv(path)
    return _FAC_DF


def mesh_intersection_weight(distance_km: float, radius_km: float, half_diag: float = MESH_HALF_DIAG_KM) -> float:
    """円とメッシュの交差を中心距離で近似した重み。"""
    if distance_km + half_diag <= radius_km:
        return 1.0
    if distance_km - half_diag >= radius_km:
        return 0.0
    # 部分交差: 線形近似
    return max(0.0, min(1.0, (radius_km - (distance_km - half_diag)) / (2 * half_diag)))


def select_meshes(lat: float, lon: float, radius_km: float) -> list[MeshContribution]:
    df = _load_mesh()
    # 粗フィルタ（緯度1度≈111km）
    ddeg = (radius_km + 1.0) / 80.0
    sub = df[
        (df["lat"] >= lat - ddeg)
        & (df["lat"] <= lat + ddeg)
        & (df["lon"] >= lon - ddeg)
        & (df["lon"] <= lon + ddeg)
    ]
    out: list[MeshContribution] = []
    for r in sub.itertuples(index=False):
        d = haversine_km(lat, lon, float(r.lat), float(r.lon))
        w = mesh_intersection_weight(d, radius_km)
        if w <= 0:
            continue
        out.append(
            MeshContribution(
                mesh_code=str(r.mesh_code),
                pref_code=str(r.pref_code).zfill(2),
                distance_km=round(d, 3),
                weight=round(w, 4),
                pop_total=float(r.pop_total) * w,
                elderly_65=float(r.elderly_65) * w,
                elderly_75=float(r.elderly_75) * w,
                elderly_85=float(r.elderly_85) * w,
                elderly_95=float(r.elderly_95) * w,
            )
        )
    return out


def select_facilities(lat: float, lon: float, radius_km: float) -> list[FacilityHit]:
    df = _load_facilities()
    ddeg = (radius_km + 1.0) / 80.0
    sub = df[
        (df["lat"] >= lat - ddeg)
        & (df["lat"] <= lat + ddeg)
        & (df["lon"] >= lon - ddeg)
        & (df["lon"] <= lon + ddeg)
    ]
    hits: list[FacilityHit] = []
    for r in sub.itertuples(index=False):
        d = haversine_km(lat, lon, float(r.lat), float(r.lon))
        if d > radius_km:
            continue
        hits.append(
            FacilityHit(
                name=str(r.name),
                service_name=str(r.service_name),
                distance_km=round(d, 2),
                capacity=float(r.capacity),
                residents_est=float(r.residents_est),
            )
        )
    hits.sort(key=lambda x: x.distance_km)
    return hits


def scale_mesh_to_2025(
    elderly_65: float,
    elderly_75: float,
    elderly_85: float,
    elderly_95: float,
    pref_codes: list[str],
) -> dict[str, float]:
    """2020メッシュ人口を社人研の同県2020→2025伸び率でスケール。"""
    try:
        with gzip.open(DATA_DIR / "municipalities_age5.json.gz", "rt", encoding="utf-8") as f:
            munis = json.load(f)
    except FileNotFoundError:
        return _split_mesh_bands(elderly_65, elderly_75, elderly_85, elderly_95)

    e2020 = e2025 = 0.0
    for m in munis:
        if m.get("pref_code") not in pref_codes:
            continue
        ages25 = m.get("ages") or {}
        ages20 = m.get("ages_2020") or {}
        keys = ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
        e2025 += sum(ages25.get(b, 0) for b in keys)
        e2020 += sum(ages20.get(b, 0) for b in keys)
    growth = (e2025 / e2020) if e2020 else 1.0
    growth = max(0.9, min(1.25, growth))
    return _split_mesh_bands(
        elderly_65 * growth,
        elderly_75 * growth,
        elderly_85 * growth,
        elderly_95 * growth,
    )


def _split_mesh_bands(e65, e75, e85, e95) -> dict[str, float]:
    return {
        "65-74": max(0.0, e65 - e75),
        "75-84": max(0.0, e75 - e85),
        "85-94": max(0.0, e85 - e95),
        "95+": max(0.0, e95),
    }


def dominant_pref(meshes: list[MeshContribution]) -> str:
    weights: dict[str, float] = {}
    for m in meshes:
        weights[m.pref_code] = weights.get(m.pref_code, 0.0) + m.elderly_65
    if not weights:
        return "13"
    return max(weights, key=weights.get)


def load_calibration(path: Path | None = None) -> dict[str, float]:
    """実績YAMLから clinic_id -> factor を読む（簡易）。"""
    path = path or (DATA_DIR / "calibration.yaml")
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    factors = {}
    for c in data.get("clinics", []):
        if c.get("calibration_factor") is not None:
            factors[c.get("id") or c.get("name")] = float(c["calibration_factor"])
    # グローバル縮小平均
    if data.get("global_calibration_factor") is not None:
        factors["__global__"] = float(data["global_calibration_factor"])
    return factors


def compute_calibration_from_actuals(
    actuals: list[dict],
    model_homes: list[float],
    shrink: float = 0.3,
) -> float:
    """実績/推計比の縮小推定平均。shrink=0.3は全国寄りに30%寄せる。"""
    ratios = []
    for a, m in zip(actuals, model_homes):
        if m and a.get("actual_home_patients"):
            ratios.append(float(a["actual_home_patients"]) / m)
    if not ratios:
        return 1.0
    mean_r = sum(ratios) / len(ratios)
    return (1.0 - shrink) * mean_r + shrink * 1.0


def estimate_precision(
    lat: float,
    lon: float,
    *,
    address: str = "",
    geocoded_name: str = "",
    radius_km: float = DEFAULT_RADIUS_KM,
    clinic_id: str | None = None,
    calibration_factor: float | None = None,
) -> PrecisionEstimationResult:
    constants = load_json("national_constants.json")
    national = load_json("national_visit_rates.json")
    pref_rates = load_json("pref_visit_rates.json")

    meshes = select_meshes(lat, lon, radius_km)
    if not meshes:
        raise ValueError("半径内にメッシュ人口がありません。座標を確認してください。")

    facilities = select_facilities(lat, lon, radius_km)
    pref = dominant_pref(meshes)
    pref_info = pref_rates["prefectures"].get(pref, {})
    intensity = float(pref_info.get("intensity_vs_national") or 1.0)

    pop_total = sum(m.pop_total for m in meshes)
    e65 = sum(m.elderly_65 for m in meshes)
    e75 = sum(m.elderly_75 for m in meshes)
    e85 = sum(m.elderly_85 for m in meshes)
    e95 = sum(m.elderly_95 for m in meshes)

    prefs_in = sorted({m.pref_code for m in meshes})
    # 2020メッシュ実数
    bands_2020 = _split_mesh_bands(e65, e75, e85, e95)
    bands = scale_mesh_to_2025(e65, e75, e85, e95, prefs_in)
    growth = (
        sum(bands.values()) / sum(bands_2020.values())
        if sum(bands_2020.values())
        else 1.0
    )

    # 受療率: 都道府県別メッシュバンド率（なければ全国）
    mesh_rates = pref_info.get("mesh_band_rates") or national.get("mesh_band_rates")
    if not mesh_rates:
        mesh_rates = national["mesh_band_rates"]

    age_estimates = []
    patients_total = patients_home_raw = patients_fac_raw = 0.0
    for band, pop in bands.items():
        rb = mesh_rates[band]
        pt = pop * rb["patient_rate_total"]
        ph = pop * rb["patient_rate_home"]
        pf = pop * rb["patient_rate_facility"]
        patients_total += pt
        patients_home_raw += ph
        patients_fac_raw += pf
        age_estimates.append({
            "band": band,
            "population": round(pop),
            "patients_total": round(pt, 1),
            "patients_home_raw": round(ph, 1),
            "patients_facility_raw": round(pf, 1),
            "rate_total": rb["patient_rate_total"],
            "rate_home": rb["patient_rate_home"],
        })

    facility_residents = sum(f.residents_est for f in facilities)
    facility_count = len(facilities)
    facility_beds = sum(f.capacity for f in facilities)

    # 同一建物補正
    sb_fac_frac = float(constants.get("same_building_facility_fraction", 0.75))
    fac_visit_rate = float(constants.get("facility_visit_rate_among_residents", 0.55))

    facility_from_ndb = patients_fac_raw * sb_fac_frac
    apartment_same_building = patients_fac_raw * (1.0 - sb_fac_frac)
    facility_from_beds = facility_residents * fac_visit_rate

    if facility_residents > 0:
        w_b = min(0.7, 0.3 + facility_residents / max(sum(bands.values()), 1) * 5)
    else:
        w_b = 0.2
    facility_true = (1 - w_b) * facility_from_ndb + w_b * facility_from_beds
    facility_true = min(facility_true, patients_total)

    home_detached = patients_home_raw
    home_total = home_detached + apartment_same_building
    home_residual = max(0.0, patients_total - facility_true)
    recommended = (home_total + home_residual) / 2.0

    # キャリブレーション
    cal = calibration_factor
    if cal is None:
        factors = load_calibration()
        if clinic_id and clinic_id in factors:
            cal = factors[clinic_id]
        elif "__global__" in factors:
            cal = factors["__global__"]
    calibrated = round(recommended * cal, 1) if cal is not None else None

    elderly_2025 = sum(bands.values())
    elderly_2020 = sum(bands_2020.values())
    quality = []
    if len(meshes) < 50:
        quality.append("WARNING: メッシュ数が少ない（郊外・海岸部の可能性）")
    if facility_residents == 0:
        quality.append("WARNING: 圏内に入居系施設座標がヒットせず（施設控除はNDB比率依存）")
    hi = float(pref_info.get("home_intensity_vs_national") or intensity)
    if hi < 0.7 or hi > 1.5:
        quality.append(f"INFO: 居宅受療強度が全国比{hi:.2f}")
    quality.append("OK: メッシュ人口×都道府県別受療率（居宅/施設分離）×施設実在座標")

    notes = [
        f"圏域: 半径{radius_km:g}kmの円と国勢調査1/4メッシュ（約250m）の交差近似。",
        f"人口: 令和2年国勢調査メッシュを社人研2025伸び率（×{growth:.3f}）で高齢者のみスケール。",
        f"受療率: NDBを都道府県の居宅強度・施設強度で別補正（{pref_info.get('name', pref)}）。",
        "居宅: NDB同一建物以外 + 同一建物のうち集合住宅分（施設由来割合で分離）。",
        "施設: 介護情報公表システムの入居系定員×稼働率とNDB施設寄り算定を統合。",
        "推奨居宅患者数 = (居宅合計 + 総需要−真施設の残差) / 2。",
    ]
    sources = list(constants.get("source", {}).values()) + [
        "OpenStreetMap Nominatim（住所ジオコーディング）",
    ]

    return PrecisionEstimationResult(
        address=address,
        geocoded_name=geocoded_name or address,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        method="mesh+pref_ndb+facility_points+same_building_split",
        demographics={
            "pop_total_2020_mesh": round(pop_total),
            "elderly_65_2020_mesh": round(elderly_2020),
            "elderly_65": round(elderly_2025),
            "elderly_75": round(bands["75-84"] + bands["85-94"] + bands["95+"]),
            "elderly_85": round(bands["85-94"] + bands["95+"]),
            "aging_rate_pct_2020": round(100.0 * elderly_2020 / pop_total, 1) if pop_total else 0.0,
            "population_growth_to_2025": round(growth, 3),
        },
        mesh_count=len(meshes),
        facility_summary={
            "facility_count": facility_count,
            "capacity_total": round(facility_beds),
            "residents_est": round(facility_residents, 1),
            "facility_patients_from_beds": round(facility_from_beds, 1),
            "facility_patients_from_ndb": round(facility_from_ndb, 1),
        },
        facilities_top=[
            {
                "name": f.name,
                "service": f.service_name,
                "distance_km": f.distance_km,
                "residents_est": f.residents_est,
            }
            for f in facilities[:15]
        ],
        age_band_estimates=age_estimates,
        visit_patients_total=round(patients_total, 1),
        visit_patients_facility_true=round(facility_true, 1),
        visit_patients_apartment_same_building=round(apartment_same_building, 1),
        visit_patients_home_detached=round(home_detached, 1),
        visit_patients_home_total=round(home_total, 1),
        recommended_home_patients=round(recommended, 1),
        recommended_home_patients_calibrated=calibrated,
        calibration_factor=cal,
        pref_intensity={
            "pref_code": pref,
            "pref_name": pref_info.get("name", ""),
            "intensity_vs_national": round(float(pref_info.get("intensity_vs_national") or 1), 3),
            "home_intensity_vs_national": round(float(pref_info.get("home_intensity_vs_national") or 1), 3),
            "facility_intensity_vs_national": round(float(pref_info.get("facility_intensity_vs_national") or 1), 3),
            "home_share": round(float(pref_info.get("home_share") or 0), 3),
        },
        quality_flags=quality,
        method_notes=notes,
        sources=sources,
    )


def estimate_precision_from_address(
    address: str,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
    lat: float | None = None,
    lon: float | None = None,
    clinic_id: str | None = None,
    calibration_factor: float | None = None,
) -> PrecisionEstimationResult:
    if lat is not None and lon is not None:
        geo = GeoPoint(lat=lat, lon=lon, display_name=address, query=address)
    else:
        geo = geocode_address(address)
    return estimate_precision(
        geo.lat,
        geo.lon,
        address=address,
        geocoded_name=geo.display_name,
        radius_km=radius_km,
        clinic_id=clinic_id,
        calibration_factor=calibration_factor,
    )


def format_precision_report(r: PrecisionEstimationResult) -> str:
    lines = []
    lines.append("=" * 76)
    lines.append("訪問診療・居宅患者数 高精度推定レポート（本部検証用）")
    lines.append("=" * 76)
    lines.append(f"住所: {r.address}")
    lines.append(f"ジオコード: {r.geocoded_name}")
    lines.append(f"座標: {r.lat:.6f}, {r.lon:.6f} / 半径 {r.radius_km:g} km")
    lines.append(f"手法: {r.method}")
    lines.append("")
    lines.append("【指標の定義】")
    lines.append("  - 本レポートの患者数は『地域の市場規模』（他院含む需要）です。")
    lines.append("  - 自院実績 ÷ 市場規模 = 獲得率。市場規模そのものに実績係数は掛けません。")
    lines.append("  - 施設の『真・施設患者』は圏内の施設市場需要であり、契約施設KPIではありません。")
    lines.append("")
    lines.append("【品質フラグ】")
    for q in r.quality_flags:
        lines.append(f"  - {q}")
    lines.append("")
    d = r.demographics
    lines.append("【人口動態（メッシュ集計→2025スケール）】")
    lines.append(
        f"  総人口(2020メッシュ): {d.get('pop_total_2020_mesh', d.get('pop_total', 0)):,.0f} 人 / "
        f"メッシュ数: {r.mesh_count}"
    )
    lines.append(
        f"  65歳以上(2020): {d.get('elderly_65_2020_mesh', 0):,.0f} → "
        f"(2025推計): {d['elderly_65']:,.0f} 人（伸び率×{d.get('population_growth_to_2025', 1)}）"
    )
    lines.append(
        f"  75歳以上: {d['elderly_75']:,.0f} 人 / 85歳以上: {d['elderly_85']:,.0f} 人 / "
        f"高齢化率(2020): {d.get('aging_rate_pct_2020', d.get('aging_rate_pct', 0))}%"
    )
    lines.append("")
    pi = r.pref_intensity
    lines.append("【地域受療強度】")
    lines.append(
        f"  主たる都道府県: {pi['pref_name']}（{pi['pref_code']}） "
        f"居宅強度 {pi.get('home_intensity_vs_national', pi.get('intensity_vs_national'))} / "
        f"施設強度 {pi.get('facility_intensity_vs_national', '-')} / "
        f"居宅シェア {pi['home_share']}"
    )
    lines.append("")
    fs = r.facility_summary
    lines.append("【圏内入居系施設（情報公表システム）】")
    lines.append(
        f"  施設数: {fs['facility_count']:,.0f} / 定員: {fs['capacity_total']:,.0f} / "
        f"入居者推計: {fs['residents_est']:,.1f}"
    )
    lines.append(
        f"  施設患者（定員法）: {fs['facility_patients_from_beds']:,.1f} / "
        f"（NDB法）: {fs['facility_patients_from_ndb']:,.1f}"
    )
    lines.append("")
    lines.append("【訪問診療需要推計＝市場規模（月間・ユニーク患者）】")
    lines.append(f"  総訪問診療市場: {r.visit_patients_total:,.1f}")
    lines.append(f"  施設市場需要: {r.visit_patients_facility_true:,.1f}")
    lines.append(f"  集合住宅（同一建物の居宅分）: {r.visit_patients_apartment_same_building:,.1f}")
    lines.append(f"  戸建等居宅（同一建物以外）: {r.visit_patients_home_detached:,.1f}")
    lines.append(f"  居宅市場合計: {r.visit_patients_home_total:,.1f}")
    lines.append("")
    lines.append(f"★ 居宅市場規模（推奨中心値）: {r.recommended_home_patients:,.1f} 人")
    if r.recommended_home_patients_calibrated is not None:
        lines.append(
            f"☆ 参考・自院獲得イメージ（市場×係数）: {r.recommended_home_patients_calibrated:,.1f} 人 "
            f"（factor={r.calibration_factor} ※市場規模の補正ではない）"
        )
    lines.append("")
    lines.append("【年齢階級別】")
    lines.append(f"  {'階級':>8} {'人口':>10} {'総患者':>10} {'居宅raw':>10} {'施設raw':>10}")
    for b in r.age_band_estimates:
        lines.append(
            f"  {b['band']:>8} {b['population']:10,.0f} {b['patients_total']:10,.1f} "
            f"{b['patients_home_raw']:10,.1f} {b['patients_facility_raw']:10,.1f}"
        )
    lines.append("")
    lines.append("【近隣施設（距離順・上位）】")
    for f in r.facilities_top:
        lines.append(
            f"  {f['distance_km']:5.2f}km  入居≈{f['residents_est']:>6.0f}  "
            f"{f['service']} / {f['name']}"
        )
    lines.append("")
    lines.append("【手法メモ】")
    for n in r.method_notes:
        lines.append(f"  - {n}")
    lines.append("")
    lines.append("【データ出典】")
    for s in r.sources:
        lines.append(f"  - {s}")
    lines.append("=" * 76)
    return "\n".join(lines)
