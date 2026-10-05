"""本部向け分析: 定義固定・圏域重複除去・期待獲得率帯・半径感度・施設KPI分離。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .estimator import haversine_km, load_json
from .precision import (
    _load_mesh,
    estimate_precision,
    mesh_intersection_weight,
    scale_mesh_to_2025,
    select_facilities,
    select_meshes,
)

# ---------------------------------------------------------------------------
# 本部定義（固定文言）
# ---------------------------------------------------------------------------

HQ_DEFINITIONS = {
    "market_home": (
        "居宅市場規模: 指定半径圏内に発生しうる居宅訪問診療患者数（他院含む地域需要）。"
        "自院の実績患者数ではない。"
    ),
    "market_facility": (
        "施設市場需要: 圏内の入居系施設に由来しうる訪問診療需要（地域全体）。"
        "自院の契約施設患者数ではない。"
    ),
    "capture_home": (
        "居宅獲得率: 自院実績居宅患者 ÷ 居宅市場規模。"
        "競合・開院年数・施設偏重の影響を受ける。"
    ),
    "facility_contract_kpi": (
        "施設契約KPI: 自院が契約・担当する施設の実績患者数。"
        "市場需要との比率（シェア）は原則使わない。"
    ),
    "exclusive_market": (
        "排他的市場: グループ院のうち当該院が最寄りとなるメッシュの需要（重複除去後）。"
    ),
    "union_market": (
        "グループ統合市場: 各院圏域のユニオン（メッシュ重複を1回だけ計上）。"
    ),
}


# 構造密度に基づく期待居宅獲得率帯（実績突合でキャリブレーションした目安）
# elderly_65_2025 は半径8km想定の目安閾値
DENSITY_SHARE_BANDS: list[dict[str, Any]] = [
    {
        "tier": "超稠密",
        "min_elderly": 500_000,
        "share_low_pct": 0.5,
        "share_high_pct": 3.0,
        "note": "都心・巨大圏。競合厚くシェアは低く見えやすい",
    },
    {
        "tier": "稠密",
        "min_elderly": 350_000,
        "share_low_pct": 1.0,
        "share_high_pct": 5.0,
        "note": "東京区部・近郊密集",
    },
    {
        "tier": "準稠密",
        "min_elderly": 250_000,
        "share_low_pct": 3.0,
        "share_high_pct": 12.0,
        "note": "郊外中核・千葉・埼玉の一部",
    },
    {
        "tier": "郊外〜中密度",
        "min_elderly": 0,
        "share_low_pct": 5.0,
        "share_high_pct": 22.0,
        "note": "相対的に獲得余地が大きい",
    },
]


@dataclass
class ClinicInput:
    id: str
    name: str
    lat: float
    lon: float
    address: str = ""
    actual_home_patients: float | None = None
    actual_facility_patients: float | None = None


@dataclass
class ClinicMarketRow:
    id: str
    name: str
    radius_km: float
    elderly_65: float
    market_home: float
    market_facility: float
    market_total: float
    facility_count: int
    facilities_per_10k_elderly: float
    density_tier: str
    expected_share_low_pct: float
    expected_share_high_pct: float
    expected_home_low: float
    expected_home_high: float
    actual_home: float | None
    actual_facility: float | None
    home_capture_pct: float | None
    capture_vs_band: str  # below / within / above / n/a
    exclusive_elderly_65: float = 0.0
    exclusive_market_home: float = 0.0
    contested_elderly_65: float = 0.0
    sibling_clinics_in_radius: int = 0
    home_visit_competitors: int = 0
    all_clinics_in_radius: int = 0
    external_competition_tier: str = ""
    clinics_per_10k_elderly: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class OverlapSummary:
    radius_km: float
    clinic_ids: list[str]
    naive_sum_elderly_65: float
    union_elderly_65: float
    overlap_elderly_65: float
    overlap_pct_of_naive: float
    naive_sum_market_home: float
    union_market_home: float
    exclusive_by_clinic: dict[str, float]
    contested_elderly_65: float
    pair_overlaps: list[dict[str, Any]]


@dataclass
class SensitivityRow:
    id: str
    name: str
    by_radius: dict[str, dict[str, float]]  # "5"|"8"|"10" -> metrics


@dataclass
class HQPipelineResult:
    definitions: dict[str, str]
    radius_km_primary: float
    clinics: list[ClinicMarketRow]
    overlap: OverlapSummary
    sensitivity: list[SensitivityRow]
    facility_kpi: list[dict[str, Any]]
    recommendations: list[str]
    action_sheets: list[dict[str, Any]] = field(default_factory=list)
    radius_policy: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def patients_from_mesh_bands(
    bands: dict[str, float],
    pref_code: str,
) -> tuple[float, float, float]:
    """年齢バンド人口 → (total, home_raw, facility_raw)。"""
    national = load_json("national_visit_rates.json")
    pref_rates = load_json("pref_visit_rates.json")
    pref_info = pref_rates["prefectures"].get(pref_code, {})
    mesh_rates = pref_info.get("mesh_band_rates") or national["mesh_band_rates"]
    total = home = fac = 0.0
    for band, pop in bands.items():
        rb = mesh_rates[band]
        total += pop * rb["patient_rate_total"]
        home += pop * rb["patient_rate_home"]
        fac += pop * rb["patient_rate_facility"]
    return total, home, fac


def recommended_home_from_raw(
    patients_total: float,
    patients_home_raw: float,
    patients_fac_raw: float,
    facility_residents: float = 0.0,
    elderly_total: float = 1.0,
) -> tuple[float, float]:
    """precision.py と同じ推奨居宅・真施設の簡易版。"""
    constants = load_json("national_constants.json")
    sb_fac_frac = float(constants.get("same_building_facility_fraction", 0.75))
    fac_visit_rate = float(constants.get("facility_visit_rate_among_residents", 0.55))
    facility_from_ndb = patients_fac_raw * sb_fac_frac
    apartment = patients_fac_raw * (1.0 - sb_fac_frac)
    facility_from_beds = facility_residents * fac_visit_rate
    if facility_residents > 0:
        w_b = min(0.7, 0.3 + facility_residents / max(elderly_total, 1) * 5)
    else:
        w_b = 0.2
    facility_true = (1 - w_b) * facility_from_ndb + w_b * facility_from_beds
    facility_true = min(facility_true, patients_total)
    home_total = patients_home_raw + apartment
    home_residual = max(0.0, patients_total - facility_true)
    recommended = (home_total + home_residual) / 2.0
    return recommended, facility_true


def density_tier_for_elderly(elderly_65: float) -> dict[str, Any]:
    for band in DENSITY_SHARE_BANDS:
        if elderly_65 >= band["min_elderly"]:
            return band
    return DENSITY_SHARE_BANDS[-1]


def adjust_share_band_for_competition(
    band: dict[str, Any],
    *,
    sibling_clinics: int,
    facilities_per_10k: float,
) -> tuple[float, float, list[str]]:
    """グループ内重複・施設密度で期待シェア帯を微調整。"""
    low = float(band["share_low_pct"])
    high = float(band["share_high_pct"])
    notes: list[str] = []
    if sibling_clinics >= 2:
        # グループ内で圏域が重なると実効シェアは下がる
        low *= 0.7
        high *= 0.75
        notes.append(f"グループ内近接院{sibling_clinics}院→期待シェア帯を下方調整")
    if facilities_per_10k >= 25:
        low *= 0.85
        high *= 0.9
        notes.append("入居系施設密度が高め→施設偏重余地・居宅競争の双方に注意")
    return round(low, 2), round(high, 2), notes


def capture_vs_band(capture_pct: float | None, low: float, high: float) -> str:
    if capture_pct is None:
        return "n/a"
    if capture_pct < low:
        return "below"
    if capture_pct > high:
        return "above"
    return "within"


def count_sibling_clinics(clinic: ClinicInput, clinics: list[ClinicInput], radius_km: float) -> int:
    n = 0
    for other in clinics:
        if other.id == clinic.id:
            continue
        if haversine_km(clinic.lat, clinic.lon, other.lat, other.lon) <= radius_km:
            n += 1
    return n


def analyze_mesh_overlap(
    clinics: list[ClinicInput],
    radius_km: float = 8.0,
) -> tuple[OverlapSummary, dict[str, dict[str, float]]]:
    """
    メッシュ単位でグループ圏域の重複を分析する。

    Returns:
      overlap summary,
      per-clinic dict with exclusive_elderly_65 / contested_elderly_65 / exclusive_home_market
    """
    # mesh_code -> {raw pops, pref, coverers: [(clinic_id, dist, weight)]}
    index: dict[str, dict[str, Any]] = {}
    df = _load_mesh()

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
                    "pref_code": str(r.pref_code).zfill(2),
                    "pop_total": float(r.pop_total),
                    "elderly_65": float(r.elderly_65),
                    "elderly_75": float(r.elderly_75),
                    "elderly_85": float(r.elderly_85),
                    "elderly_95": float(r.elderly_95),
                    "coverers": [],
                }
            index[code]["coverers"].append((c.id, d, w))

    # naive sum: each clinic independently (approx via select_meshes)
    naive_elderly = 0.0
    naive_home = 0.0
    per_clinic_naive_home: dict[str, float] = {}
    for c in clinics:
        meshes = select_meshes(c.lat, c.lon, radius_km)
        e65 = sum(m.elderly_65 for m in meshes)
        e75 = sum(m.elderly_75 for m in meshes)
        e85 = sum(m.elderly_85 for m in meshes)
        e95 = sum(m.elderly_95 for m in meshes)
        prefs = sorted({m.pref_code for m in meshes})
        bands = scale_mesh_to_2025(e65, e75, e85, e95, prefs)
        weights: dict[str, float] = {}
        for m in meshes:
            weights[m.pref_code] = weights.get(m.pref_code, 0.0) + m.elderly_65
        pref = max(weights, key=weights.get) if weights else "13"
        total, home_raw, fac_raw = patients_from_mesh_bands(bands, pref)
        facs = select_facilities(c.lat, c.lon, radius_km)
        residents = sum(f.residents_est for f in facs)
        rec, _ = recommended_home_from_raw(
            total, home_raw, fac_raw, residents, sum(bands.values())
        )
        naive_elderly += sum(bands.values())
        naive_home += rec
        per_clinic_naive_home[c.id] = rec

    # union / exclusive / contested
    union_e65 = union_e75 = union_e85 = union_e95 = 0.0
    pref_weights: dict[str, float] = {}
    exclusive_elderly: dict[str, float] = {c.id: 0.0 for c in clinics}
    contested_e65 = 0.0
    exclusive_raw: dict[str, dict[str, float]] = {
        c.id: {"e65": 0.0, "e75": 0.0, "e85": 0.0, "e95": 0.0, "pref_w": {}}
        for c in clinics
    }

    for meta in index.values():
        coverers = meta["coverers"]
        max_w = max(w for _, _, w in coverers)
        e65 = meta["elderly_65"] * max_w
        e75 = meta["elderly_75"] * max_w
        e85 = meta["elderly_85"] * max_w
        e95 = meta["elderly_95"] * max_w
        union_e65 += e65
        union_e75 += e75
        union_e85 += e85
        union_e95 += e95
        pref_weights[meta["pref_code"]] = pref_weights.get(meta["pref_code"], 0.0) + e65

        owner_id = min(coverers, key=lambda t: (t[1], t[0]))[0]
        if len(coverers) >= 2:
            contested_e65 += e65
        exclusive_elderly[owner_id] += e65
        er = exclusive_raw[owner_id]
        er["e65"] += e65
        er["e75"] += e75
        er["e85"] += e85
        er["e95"] += e95
        pw = er["pref_w"]
        pw[meta["pref_code"]] = pw.get(meta["pref_code"], 0.0) + e65

    # scale union to 2025 and estimate market once
    prefs_u = sorted(pref_weights.keys())
    bands_u = scale_mesh_to_2025(union_e65, union_e75, union_e85, union_e95, prefs_u)
    pref_u = max(pref_weights, key=pref_weights.get) if pref_weights else "13"
    total_u, home_u, fac_u = patients_from_mesh_bands(bands_u, pref_u)
    union_home, _ = recommended_home_from_raw(
        total_u, home_u, fac_u, 0.0, sum(bands_u.values())
    )
    union_elderly_2025 = sum(bands_u.values())

    # exclusive home market per clinic
    per_clinic: dict[str, dict[str, float]] = {}
    for c in clinics:
        er = exclusive_raw[c.id]
        prefs_c = sorted(er["pref_w"].keys())
        bands_c = scale_mesh_to_2025(er["e65"], er["e75"], er["e85"], er["e95"], prefs_c or ["13"])
        pref_c = max(er["pref_w"], key=er["pref_w"].get) if er["pref_w"] else "13"
        tot, hm, fc = patients_from_mesh_bands(bands_c, pref_c)
        rec, _ = recommended_home_from_raw(tot, hm, fc, 0.0, sum(bands_c.values()))
        per_clinic[c.id] = {
            "exclusive_elderly_65": round(sum(bands_c.values()), 1),
            "exclusive_market_home": round(rec, 1),
            "contested_elderly_65": 0.0,  # filled below proportionally
        }

    # contested attributed by nearest ownership already in exclusive;
    # report global contested separately; per-clinic contested = elderly in meshes with 2+ coverers where this clinic covers
    contested_by_clinic: dict[str, float] = {c.id: 0.0 for c in clinics}
    for meta in index.values():
        coverers = meta["coverers"]
        if len(coverers) < 2:
            continue
        max_w = max(w for _, _, w in coverers)
        e65 = meta["elderly_65"] * max_w
        # scale factor approx: use union growth
        growth = union_elderly_2025 / union_e65 if union_e65 else 1.0
        for cid, _, _ in coverers:
            contested_by_clinic[cid] += e65 * growth

    for cid, v in contested_by_clinic.items():
        per_clinic[cid]["contested_elderly_65"] = round(v, 1)

    # pair overlaps (elderly in intersection)
    pair_map: dict[tuple[str, str], float] = {}
    for meta in index.values():
        ids = sorted({cid for cid, _, _ in meta["coverers"]})
        if len(ids) < 2:
            continue
        max_w = max(w for _, _, w in meta["coverers"])
        e65 = meta["elderly_65"] * max_w
        growth = union_elderly_2025 / union_e65 if union_e65 else 1.0
        e = e65 * growth
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (ids[i], ids[j])
                pair_map[key] = pair_map.get(key, 0.0) + e

    id_to_name = {c.id: c.name for c in clinics}
    pair_overlaps = [
        {
            "clinic_a": a,
            "clinic_b": b,
            "name_a": id_to_name.get(a, a),
            "name_b": id_to_name.get(b, b),
            "overlap_elderly_65": round(v, 1),
        }
        for (a, b), v in sorted(pair_map.items(), key=lambda x: -x[1])[:20]
    ]

    overlap_elderly = max(0.0, naive_elderly - union_elderly_2025)
    summary = OverlapSummary(
        radius_km=radius_km,
        clinic_ids=[c.id for c in clinics],
        naive_sum_elderly_65=round(naive_elderly, 1),
        union_elderly_65=round(union_elderly_2025, 1),
        overlap_elderly_65=round(overlap_elderly, 1),
        overlap_pct_of_naive=round(100.0 * overlap_elderly / naive_elderly, 1) if naive_elderly else 0.0,
        naive_sum_market_home=round(naive_home, 1),
        union_market_home=round(union_home, 1),
        exclusive_by_clinic={k: v["exclusive_market_home"] for k, v in per_clinic.items()},
        contested_elderly_65=round(
            contested_e65 * (union_elderly_2025 / union_e65 if union_e65 else 1.0), 1
        ),
        pair_overlaps=pair_overlaps,
    )
    return summary, per_clinic


def build_clinic_market_row(
    clinic: ClinicInput,
    clinics: list[ClinicInput],
    radius_km: float,
    exclusive: dict[str, float] | None = None,
) -> ClinicMarketRow:
    from .competition import adjust_share_for_external_competition, competition_metrics

    r = estimate_precision(
        clinic.lat,
        clinic.lon,
        address=clinic.address or clinic.name,
        radius_km=radius_km,
        clinic_id=clinic.id,
        calibration_factor=None,  # 市場規模にはキャリブレーションを掛けない
    )
    elderly = float(r.demographics["elderly_65"])
    band = density_tier_for_elderly(elderly)
    siblings = count_sibling_clinics(clinic, clinics, radius_km)
    fac_per_10k = (
        10000.0 * r.facility_summary["facility_count"] / elderly if elderly else 0.0
    )
    low, high, notes = adjust_share_band_for_competition(
        band, sibling_clinics=siblings, facilities_per_10k=fac_per_10k
    )
    comp = competition_metrics(clinic.lat, clinic.lon, radius_km, elderly)
    low, high, ext_notes = adjust_share_for_external_competition(low, high, comp)
    notes = notes + ext_notes
    market_home = float(r.recommended_home_patients)
    actual_home = clinic.actual_home_patients
    capture = (
        100.0 * actual_home / market_home
        if actual_home is not None and market_home
        else None
    )
    excl = exclusive or {}
    return ClinicMarketRow(
        id=clinic.id,
        name=clinic.name,
        radius_km=radius_km,
        elderly_65=elderly,
        market_home=market_home,
        market_facility=float(r.visit_patients_facility_true),
        market_total=float(r.visit_patients_total),
        facility_count=int(r.facility_summary["facility_count"]),
        facilities_per_10k_elderly=round(fac_per_10k, 2),
        density_tier=str(band["tier"]),
        expected_share_low_pct=low,
        expected_share_high_pct=high,
        expected_home_low=round(market_home * low / 100.0, 1),
        expected_home_high=round(market_home * high / 100.0, 1),
        actual_home=actual_home,
        actual_facility=clinic.actual_facility_patients,
        home_capture_pct=round(capture, 2) if capture is not None else None,
        capture_vs_band=capture_vs_band(capture, low, high),
        exclusive_elderly_65=float(excl.get("exclusive_elderly_65", 0.0)),
        exclusive_market_home=float(excl.get("exclusive_market_home", 0.0)),
        contested_elderly_65=float(excl.get("contested_elderly_65", 0.0)),
        sibling_clinics_in_radius=siblings,
        home_visit_competitors=int(comp["home_visit_competitors"]),
        all_clinics_in_radius=int(comp["all_clinics_in_radius"]),
        external_competition_tier=str(comp["external_competition_tier"]),
        clinics_per_10k_elderly=float(comp["clinics_per_10k_elderly"]),
        notes=notes + [str(band.get("note", ""))],
    )


def run_radius_sensitivity(
    clinics: list[ClinicInput],
    radii: list[float] | None = None,
) -> list[SensitivityRow]:
    radii = radii or [5.0, 8.0, 10.0]
    rows: list[SensitivityRow] = []
    for c in clinics:
        by_r: dict[str, dict[str, float]] = {}
        for rad in radii:
            r = estimate_precision(
                c.lat,
                c.lon,
                address=c.address or c.name,
                radius_km=rad,
                clinic_id=c.id,
                calibration_factor=None,
            )
            market_home = float(r.recommended_home_patients)
            actual = c.actual_home_patients
            capture = (
                100.0 * actual / market_home if actual is not None and market_home else None
            )
            by_r[f"{rad:g}"] = {
                "elderly_65": float(r.demographics["elderly_65"]),
                "market_home": market_home,
                "market_facility": float(r.visit_patients_facility_true),
                "home_capture_pct": round(capture, 2) if capture is not None else -1.0,
            }
        rows.append(SensitivityRow(id=c.id, name=c.name, by_radius=by_r))
    return rows


def build_facility_kpi(clinics: list[ClinicInput], market_rows: list[ClinicMarketRow]) -> list[dict[str, Any]]:
    """施設は契約KPIと市場需要を分離して返す。"""
    market_by_id = {r.id: r for r in market_rows}
    out = []
    for c in clinics:
        m = market_by_id[c.id]
        actual_fac = c.actual_facility_patients
        actual_home = c.actual_home_patients
        panel = (actual_fac or 0) + (actual_home or 0)
        out.append({
            "id": c.id,
            "name": c.name,
            "contract_facility_patients": actual_fac,
            "contract_home_patients": actual_home,
            "panel_total": panel if panel else None,
            "facility_share_of_panel_pct": (
                round(100.0 * actual_fac / panel, 1)
                if actual_fac is not None and panel
                else None
            ),
            "market_facility_demand": m.market_facility,
            "note": (
                "施設の市場シェア（契約÷市場需要）は用いない。"
                "施設は契約患者数とパネル内構成比で評価する。"
            ),
        })
    return out


def build_recommendations(rows: list[ClinicMarketRow], overlap: OverlapSummary) -> list[str]:
    recs = [
        (
            f"グループ8km単純合算の65+は {overlap.naive_sum_elderly_65:,.0f} 人だが、"
            f"重複除去後は {overlap.union_elderly_65:,.0f} 人"
            f"（二重計上 {overlap.overlap_pct_of_naive:.1f}%）。"
        ),
        (
            f"居宅市場も単純合算 {overlap.naive_sum_market_home:,.0f} → "
            f"ユニオン {overlap.union_market_home:,.0f}。"
            "グループポテンシャルはユニオンを用いること。"
        ),
        "院間比較の標準半径は8km。5kmは近傍コア、10kmは広域ポテンシャルの補助指標。",
        "施設は契約患者・パネル構成比で評価し、施設市場需要とのシェアは用いない。",
    ]
    for r in rows:
        if r.id == "urawa":
            recs.append("浦和: 開院直後のため獲得率の低さは立ち上がり要因。期待帯との差は経過観察。")
            continue
        if r.capture_vs_band == "below" and r.home_capture_pct is not None:
            recs.append(
                f"{r.name}: 居宅獲得率 {r.home_capture_pct:.1f}% が期待帯 "
                f"{r.expected_share_low_pct}–{r.expected_share_high_pct}% を下回る"
                f"（{r.density_tier}）。居宅開拓または圏域再定義を検討。"
            )
        elif r.capture_vs_band == "above" and r.home_capture_pct is not None:
            recs.append(
                f"{r.name}: 居宅獲得率 {r.home_capture_pct:.1f}% が期待帯上限超え。"
                "強い獲得、または推計圏が実態より広い可能性。"
            )
        if r.sibling_clinics_in_radius >= 2:
            recs.append(
                f"{r.name}: 半径内にグループ他院が {r.sibling_clinics_in_radius} 院。"
                f"排他的居宅市場≈{r.exclusive_market_home:,.0f} を院別KPIの補助に。"
            )
    return recs


RADIUS_POLICY = {
    "standard_km": "8",
    "core_km": "5",
    "wide_km": "10",
    "rule": (
        "院間比較・本部定例の標準半径は8km。"
        "5kmは近傍コア（獲得の強さ）、10kmは広域ポテンシャルの補助指標。"
        "院間比較は必ず同一半径で行う。"
    ),
    "when_to_use_5km": "立ち上げ初期・強い獲得院の再現範囲の確認・営業コア設計",
    "when_to_use_10km": "出店検討の広域需要・遠方紹介の余地確認（獲得率は参考）",
    "do_not": "半径を院ごとに変えてランキングする / 10km市場を短期目標の母数にする",
}


def run_hq_pipeline(
    clinics: list[ClinicInput],
    *,
    primary_radius_km: float = 8.0,
    sensitivity_radii: list[float] | None = None,
) -> HQPipelineResult:
    from .action_sheets import action_sheets_to_dicts, build_action_sheets

    overlap, per_clinic = analyze_mesh_overlap(clinics, primary_radius_km)
    rows = [
        build_clinic_market_row(c, clinics, primary_radius_km, per_clinic.get(c.id))
        for c in clinics
    ]
    sensitivity = run_radius_sensitivity(clinics, sensitivity_radii or [5.0, 8.0, 10.0])
    facility_kpi = build_facility_kpi(clinics, rows)
    recommendations = build_recommendations(rows, overlap)
    result = HQPipelineResult(
        definitions=dict(HQ_DEFINITIONS),
        radius_km_primary=primary_radius_km,
        clinics=rows,
        overlap=overlap,
        sensitivity=sensitivity,
        facility_kpi=facility_kpi,
        recommendations=recommendations,
        radius_policy=dict(RADIUS_POLICY),
    )
    result.action_sheets = action_sheets_to_dicts(build_action_sheets(result))
    return result


def format_hq_report(result: HQPipelineResult) -> str:
    lines: list[str] = []
    lines.append("=" * 100)
    lines.append("わかさクリニックグループ 本部向け地域分析レポート")
    lines.append("=" * 100)
    lines.append(f"主半径: {result.radius_km_primary:g} km")
    lines.append("")
    lines.append("【0. 指標の定義（固定）】")
    for key, text in result.definitions.items():
        lines.append(f"  - [{key}] {text}")
    lines.append("")

    # 1 already in definitions; 2 overlap
    o = result.overlap
    lines.append("【1. 圏域重複除去（メッシュ・ユニオン）】")
    lines.append(
        f"  単純合算 65+: {o.naive_sum_elderly_65:>12,.0f}  /  "
        f"ユニオン 65+: {o.union_elderly_65:>12,.0f}  /  "
        f"二重計上: {o.overlap_elderly_65:,.0f}（{o.overlap_pct_of_naive:.1f}%）"
    )
    lines.append(
        f"  単純合算 居宅市場: {o.naive_sum_market_home:>10,.0f}  /  "
        f"ユニオン 居宅市場: {o.union_market_home:>10,.0f}"
    )
    lines.append(f"  係争メッシュ高齢者（2院以上がカバー）: {o.contested_elderly_65:,.0f}")
    lines.append("  院ペア重複（65+上位）:")
    for p in o.pair_overlaps[:10]:
        lines.append(
            f"    {p['name_a']} × {p['name_b']}: {p['overlap_elderly_65']:,.0f} 人"
        )
    lines.append("")

    lines.append("【2. 院別市場・期待獲得率帯・実績・在支診競合】")
    lines.append(
        f"{'院名':<8} {'密度帯':<8} {'在支診':>6} {'市場居宅':>8} {'期待帯%':>10} "
        f"{'実績居宅':>8} {'獲得率%':>8} {'判定':>6} {'排他居宅':>8}"
    )
    lines.append("-" * 100)
    for r in result.clinics:
        band = f"{r.expected_share_low_pct:g}-{r.expected_share_high_pct:g}"
        ah = f"{r.actual_home:.0f}" if r.actual_home is not None else "-"
        cap = f"{r.home_capture_pct:.1f}" if r.home_capture_pct is not None else "-"
        lines.append(
            f"{r.name:<8} {r.density_tier:<8} {r.home_visit_competitors:>6} {r.market_home:>8.0f} "
            f"{band:>10} {ah:>8} {cap:>8} {r.capture_vs_band:>6} {r.exclusive_market_home:>8.0f}"
        )
    lines.append(
        "  ※在支診=関東信越厚生局 届出受理の在宅療養支援診療所（座標突合できた件数・自院名除外）"
    )
    lines.append("")
    lines.append("【3. 半径感度（5 / 8 / 10 km）】")
    lines.append(
        f"{'院名':<8} "
        f"{'5km居宅':>8} {'5km獲得%':>8} "
        f"{'8km居宅':>8} {'8km獲得%':>8} "
        f"{'10km居宅':>8} {'10km獲得%':>8}"
    )
    lines.append("-" * 100)
    for s in result.sensitivity:
        def cell(rad: str, key: str) -> str:
            v = s.by_radius.get(rad, {}).get(key, -1)
            if key == "home_capture_pct":
                return f"{v:.1f}" if v >= 0 else "-"
            return f"{v:.0f}"

        lines.append(
            f"{s.name:<8} "
            f"{cell('5', 'market_home'):>8} {cell('5', 'home_capture_pct'):>8} "
            f"{cell('8', 'market_home'):>8} {cell('8', 'home_capture_pct'):>8} "
            f"{cell('10', 'market_home'):>8} {cell('10', 'home_capture_pct'):>8}"
        )
    lines.append("")
    lines.append("  読み方: 半径を広げると市場は増えるが獲得率は下がる。院間比較は同一半径で行う。")
    lines.append("  標準半径の推奨はレポート末尾の所見を参照。")
    lines.append("")

    lines.append("【4. 施設KPI（契約）と施設市場需要の分離】")
    lines.append(
        f"{'院名':<8} {'契約施設':>8} {'契約居宅':>8} {'施設/パネル%':>10} {'施設市場需要':>10}"
    )
    lines.append("-" * 64)
    for f in result.facility_kpi:
        cf = f"{f['contract_facility_patients']:.0f}" if f["contract_facility_patients"] is not None else "-"
        ch = f"{f['contract_home_patients']:.0f}" if f["contract_home_patients"] is not None else "-"
        sp = f"{f['facility_share_of_panel_pct']:.1f}" if f["facility_share_of_panel_pct"] is not None else "-"
        lines.append(
            f"{f['name']:<8} {cf:>8} {ch:>8} {sp:>10} {f['market_facility_demand']:>10.0f}"
        )
    lines.append("  ※施設は契約患者・パネル構成で評価。市場需要とのシェアは使わない。")
    lines.append("")

    lines.append("【5. 所見・次アクション】")
    if result.radius_policy:
        lines.append(f"  - 半径ルール: {result.radius_policy.get('rule', '')}")
    # radius recommendation heuristic
    ratios = []
    for s in result.sensitivity:
        m8 = s.by_radius.get("8", {}).get("market_home") or 0
        m10 = s.by_radius.get("10", {}).get("market_home") or 0
        if m8:
            ratios.append(m10 / m8)
    if ratios:
        avg_10 = sum(ratios) / len(ratios)
        lines.append(
            f"  - 半径感度: 10km市場 / 8km市場 の平均比 ≈ {avg_10:.2f}。"
            " 標準は8km維持（比較の母数を固定）。"
        )
    for rec in result.recommendations:
        lines.append(f"  - {rec}")
    if result.action_sheets:
        lines.append("")
        lines.append("【6. アクションシート要約】")
        for a in result.action_sheets:
            if a.get("clinic_id") == "cluster_mitaka" or a.get("decision") in ("やる", "横展開"):
                lines.append(
                    f"  - [{a['decision']}/{a['priority']}] {a['clinic_name']}: {a['rationale']}"
                )
    lines.append("=" * 100)
    return "\n".join(lines)

def clinics_from_actuals_yaml(data: dict) -> list[ClinicInput]:
    out: list[ClinicInput] = []
    for c in data.get("clinics", []):
        out.append(
            ClinicInput(
                id=str(c["id"]),
                name=str(c["name"]),
                lat=float(c["lat"]),
                lon=float(c["lon"]),
                address=str(c.get("address") or ""),
                actual_home_patients=(
                    float(c["actual_home_patients"])
                    if c.get("actual_home_patients") is not None
                    else None
                ),
                actual_facility_patients=(
                    float(c["actual_facility_patients"])
                    if c.get("actual_facility_patients") is not None
                    else None
                ),
            )
        )
    return out
