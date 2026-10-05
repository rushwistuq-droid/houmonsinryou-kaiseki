"""訪問診療・居宅患者数の地域推定ロジック。"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
DEFAULT_RADIUS_KM = 8.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def load_json(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} がありません。先に scripts/build_datasets.py を実行してください。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class GeoPoint:
    lat: float
    lon: float
    display_name: str
    query: str


@dataclass
class MunicipalityContribution:
    code: str
    pref: str
    name: str
    distance_km: float
    weight: float
    pop_total: float
    elderly_65: float
    elderly_75: float
    elderly_65_74: float


@dataclass
class AgeBandEstimate:
    band: str
    population: float
    patients_total: float
    patients_home: float
    patients_facility: float
    rate_total: float
    rate_home: float


@dataclass
class EstimationResult:
    address: str
    geocoded_name: str
    lat: float
    lon: float
    radius_km: float
    catchment: list[MunicipalityContribution]
    demographics: dict[str, float]
    age_band_estimates: list[AgeBandEstimate]
    visit_patients_total: float
    visit_patients_home_ndb: float
    visit_patients_facility_ndb: float
    facility_residents_est: float
    home_elderly_est: float
    visit_patients_home_residual: float
    recommended_home_patients: float
    method_notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def geocode_address(
    address: str,
    timeout: float = 20.0,
    municipalities: list[dict] | None = None,
) -> GeoPoint:
    """Nominatim（OpenStreetMap）で住所を緯度経度に変換。

    失敗時は市区町村名をデータセットの代表点にフォールバックする。
    """
    queries = [address]
    # 番地が厳しすぎる場合に備え、段階的にクエリを緩める
    compact = address.replace(" ", "").replace("　", "")
    m = re.search(r"^(.+?[都道府県].+?[市区町村].+?)(\d.*)?$", compact)
    if m and m.group(1) and m.group(1) not in queries:
        queries.append(m.group(1))
    m2 = re.search(r"^(.+?[都道府県].+?[市区町村])", compact)
    if m2 and m2.group(1) not in queries:
        queries.append(m2.group(1))

    last_error = None
    for q in queries:
        params = urllib.parse.urlencode(
            {
                "q": q,
                "format": "json",
                "limit": 1,
                "addressdetails": 0,
                "countrycodes": "jp",
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "home-visit-demand-estimator/1.0 (research; contact: local)",
                "Accept-Language": "ja",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if data:
            hit = data[0]
            return GeoPoint(
                lat=float(hit["lat"]),
                lon=float(hit["lon"]),
                display_name=hit.get("display_name", q),
                query=address,
            )

    # オフラインフォールバック: 都道府県+市区町村名で代表点を探す
    munis = municipalities if municipalities is not None else load_json("municipalities.json")
    hit = _match_municipality(compact, munis)
    if hit:
        return GeoPoint(
            lat=hit["lat"],
            lon=hit["lon"],
            display_name=f"{hit['pref']}{hit['name']}（市区町村代表点フォールバック）",
            query=address,
        )

    detail = f" ({last_error})" if last_error else ""
    raise ValueError(f"住所をジオコーディングできませんでした: {address}{detail}")


def _match_municipality(compact_address: str, municipalities: list[dict]) -> dict | None:
    """住所文字列から最長一致の市区町村を返す。"""
    best = None
    best_len = 0
    for m in municipalities:
        label = f"{m['pref']}{m['name']}"
        if label in compact_address and len(label) > best_len:
            best = m
            best_len = len(label)
        elif m["name"] in compact_address and len(m["name"]) > best_len:
            # 同名市区町村の誤爆を減らすため、prefが含まれていれば優先
            if m["pref"] in compact_address:
                best = m
                best_len = len(m["name"])
    return best


def catchment_weight(distance_km: float, radius_km: float) -> float:
    """市区町村代表点までの距離から圏内取り込み重みを算出。

    - 半径内は距離に応じて減衰（中心=1.0、境界=0.35）
    - 半径外は含めない
    """
    if distance_km > radius_km:
        return 0.0
    # 線形減衰: 境界でも一定割合を残す（市区町村ポリゴンの一部交差を近似）
    return 1.0 - 0.65 * (distance_km / radius_km)


def select_catchment(
    lat: float,
    lon: float,
    municipalities: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
) -> list[MunicipalityContribution]:
    out: list[MunicipalityContribution] = []
    for m in municipalities:
        d = haversine_km(lat, lon, m["lat"], m["lon"])
        w = catchment_weight(d, radius_km)
        if w <= 0:
            continue
        out.append(
            MunicipalityContribution(
                code=m["code"],
                pref=m["pref"],
                name=m["name"],
                distance_km=round(d, 2),
                weight=round(w, 4),
                pop_total=m["pop_total_2025"] * w,
                elderly_65=m["elderly_65_2025"] * w,
                elderly_75=m["elderly_75_2025"] * w,
                elderly_65_74=m["elderly_65_74_2025"] * w,
            )
        )
    out.sort(key=lambda x: x.distance_km)
    return out


def expand_age_bands(
    elderly_65_74: float,
    elderly_75: float,
    constants: dict,
) -> dict[str, float]:
    """市区町村の65-74 / 75+ を全国年齢構造で細分化。"""
    s6574 = constants["share_within_65_74"]
    s75 = constants["share_within_75plus"]
    return {
        "65-69": elderly_65_74 * s6574["65-69"],
        "70-74": elderly_65_74 * s6574["70-74"],
        "75-79": elderly_75 * s75["75-79"],
        "80-84": elderly_75 * s75["80-84"],
        "85-89": elderly_75 * s75["85-89"],
        "90+": elderly_75 * s75["90+"],
    }


def estimate_from_point(
    lat: float,
    lon: float,
    *,
    address: str = "",
    geocoded_name: str = "",
    radius_km: float = DEFAULT_RADIUS_KM,
    facility_beds_override: float | None = None,
    rates: dict | None = None,
    constants: dict | None = None,
    municipalities: list[dict] | None = None,
) -> EstimationResult:
    rates = rates or load_json("national_visit_rates.json")
    constants = constants or load_json("national_constants.json")
    municipalities = municipalities or load_json("municipalities.json")

    catchment = select_catchment(lat, lon, municipalities, radius_km)
    if not catchment:
        raise ValueError("半径内に市区町村データがありません。座標または半径を確認してください。")

    pop_total = sum(c.pop_total for c in catchment)
    elderly_65 = sum(c.elderly_65 for c in catchment)
    elderly_75 = sum(c.elderly_75 for c in catchment)
    elderly_65_74 = sum(c.elderly_65_74 for c in catchment)

    age_pops = expand_age_bands(elderly_65_74, elderly_75, constants)
    # 65歳未満は訪問診療の寄与が小さいため、簡易に全国率×総人口比率は使わず
    # 高齢者バンドのみで需要の大宗を推計（NDB上も患者の大半が65歳以上）

    band_estimates: list[AgeBandEstimate] = []
    patients_total = 0.0
    patients_home = 0.0
    patients_fac = 0.0
    for band, pop in age_pops.items():
        rb = rates["age_bands"][band]
        pt = pop * rb["patient_rate_total"]
        ph = pop * rb["patient_rate_home"]
        pf = pop * rb["patient_rate_facility"]
        patients_total += pt
        patients_home += ph
        patients_fac += pf
        band_estimates.append(
            AgeBandEstimate(
                band=band,
                population=round(pop),
                patients_total=round(pt, 1),
                patients_home=round(ph, 1),
                patients_facility=round(pf, 1),
                rate_total=rb["patient_rate_total"],
                rate_home=rb["patient_rate_home"],
            )
        )

    # 施設入居者推計
    if facility_beds_override is not None:
        # 利用率92%前後を適用
        facility_residents = facility_beds_override * 0.92
        method_fac = "入力された入所定員×稼働率0.92"
    else:
        facility_residents = elderly_65 * constants["facility_residents_per_elderly_65"]
        method_fac = "65歳以上人口×全国の入居系施設入所率（介護保険施設+特定施設・GH概数）"

    home_elderly = max(0.0, elderly_65 - facility_residents)

    # 残差法: 総訪問診療需要 − 施設側NDB推計
    # ただし施設入所率が高い地域では施設側が総需要を上回る場合があるため下限0
    home_residual = max(0.0, patients_total - patients_fac)

    # 推奨値: NDB同一建物以外率による居宅推計と、施設控除残差の平均を中心に
    # （両手法のブレを明示するため中央値的に平均）
    recommended = (patients_home + home_residual) / 2.0

    notes = [
        f"圏域: 中心から半径{radius_km:g}km。市区町村代表点距離に応じた重み付き集計。",
        "人口: 社人研『日本の地域別将来推計人口（令和5年推計）』2025年値。",
        "受療率: 第10回NDBオープンデータ在宅患者訪問診療料の年齢別算定回数÷人口÷月あたり算定回数1.90。",
        "居宅/施設: NDBの『同一建物居住者以外』を居宅、『同一建物』+訪問診療料（２）を施設寄りと定義。",
        f"施設入居者: {method_fac}。介護保険施設に加え特定施設・GH概数を含む全国入居率を使用。",
        "推奨居宅患者数 = (NDB居宅推計 + 総需要−施設需要の残差) / 2。",
    ]
    sources = [
        rates["source"].get("ndb", ""),
        rates["source"].get("population", ""),
        "国立社会保障・人口問題研究所 日本の地域別将来推計人口（令和5年推計）",
        constants.get("source", {}).get("facilities")
        or constants.get("source", {}).get("care_facilities", ""),
        constants.get("source", {}).get("social_medical_stats")
        or "厚生労働省 2023年社会医療診療行為別統計",
        "OpenStreetMap Nominatim（住所ジオコーディング）",
        "Wikidata（市区町村代表座標）",
    ]
    sources = [s for s in sources if s]

    return EstimationResult(
        address=address,
        geocoded_name=geocoded_name or address,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        catchment=catchment,
        demographics={
            "pop_total": round(pop_total),
            "elderly_65": round(elderly_65),
            "elderly_75": round(elderly_75),
            "elderly_65_74": round(elderly_65_74),
            "aging_rate_pct": round(100.0 * elderly_65 / pop_total, 1) if pop_total else 0.0,
        },
        age_band_estimates=band_estimates,
        visit_patients_total=round(patients_total, 1),
        visit_patients_home_ndb=round(patients_home, 1),
        visit_patients_facility_ndb=round(patients_fac, 1),
        facility_residents_est=round(facility_residents, 1),
        home_elderly_est=round(home_elderly, 1),
        visit_patients_home_residual=round(home_residual, 1),
        recommended_home_patients=round(recommended, 1),
        method_notes=notes,
        sources=sources,
    )


def estimate_from_address(
    address: str,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
    lat: float | None = None,
    lon: float | None = None,
    facility_beds_override: float | None = None,
) -> EstimationResult:
    if lat is not None and lon is not None:
        geo = GeoPoint(lat=lat, lon=lon, display_name=address, query=address)
    else:
        geo = geocode_address(address)
    return estimate_from_point(
        geo.lat,
        geo.lon,
        address=address,
        geocoded_name=geo.display_name,
        radius_km=radius_km,
        facility_beds_override=facility_beds_override,
    )


def format_report(result: EstimationResult) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("訪問診療・居宅患者数 地域推定レポート")
    lines.append("=" * 72)
    lines.append(f"住所: {result.address}")
    lines.append(f"ジオコード: {result.geocoded_name}")
    lines.append(f"座標: {result.lat:.6f}, {result.lon:.6f}")
    lines.append(f"半径: {result.radius_km:g} km")
    lines.append("")
    lines.append("【人口動態（重み付き）】")
    d = result.demographics
    lines.append(f"  総人口: {d['pop_total']:,.0f} 人")
    lines.append(f"  65歳以上: {d['elderly_65']:,.0f} 人（高齢化率 {d['aging_rate_pct']}%）")
    lines.append(f"  65–74歳: {d['elderly_65_74']:,.0f} 人")
    lines.append(f"  75歳以上: {d['elderly_75']:,.0f} 人")
    lines.append("")
    lines.append("【訪問診療需要推計（月間・ユニーク患者）】")
    lines.append(f"  総訪問診療患者数: {result.visit_patients_total:,.1f} 人")
    lines.append(f"  うち居宅（NDB同一建物以外）: {result.visit_patients_home_ndb:,.1f} 人")
    lines.append(f"  うち施設寄り（NDB同一建物等）: {result.visit_patients_facility_ndb:,.1f} 人")
    lines.append("")
    lines.append("【施設控除による居宅推計】")
    lines.append(f"  施設入居者推計: {result.facility_residents_est:,.1f} 人")
    lines.append(f"  居宅高齢者（65歳以上−施設）: {result.home_elderly_est:,.1f} 人")
    lines.append(f"  総需要−施設需要の残差: {result.visit_patients_home_residual:,.1f} 人")
    lines.append("")
    lines.append(f"★ 推奨・推定居宅訪問診療患者数: {result.recommended_home_patients:,.1f} 人")
    lines.append("")
    lines.append("【年齢階級別内訳】")
    lines.append(
        f"  {'階級':>8} {'人口':>10} {'総患者':>10} {'居宅':>10} {'施設':>10} {'居宅率':>10}"
    )
    for b in result.age_band_estimates:
        lines.append(
            f"  {b.band:>8} {b.population:10,.0f} {b.patients_total:10,.1f} "
            f"{b.patients_home:10,.1f} {b.patients_facility:10,.1f} {b.rate_home:10.4%}"
        )
    lines.append("")
    lines.append("【圏内市区町村（距離順・上位15）】")
    for c in result.catchment[:15]:
        lines.append(
            f"  {c.distance_km:5.2f}km  w={c.weight:.2f}  {c.pref}{c.name}  "
            f"65+={c.elderly_65:,.0f}"
        )
    if len(result.catchment) > 15:
        lines.append(f"  …他 {len(result.catchment) - 15} 市区町村")
    lines.append("")
    lines.append("【手法メモ】")
    for n in result.method_notes:
        lines.append(f"  - {n}")
    lines.append("")
    lines.append("【データ出典】")
    for s in result.sources:
        lines.append(f"  - {s}")
    lines.append("=" * 72)
    return "\n".join(lines)
