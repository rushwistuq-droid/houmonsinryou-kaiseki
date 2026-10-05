#!/usr/bin/env python3
"""精度向上用データを一括構築する。

- JMAP市区町村の在支診・在支病を施設点として取得し GSI でジオコード
- NDB都道府県別の居宅/施設シェア
- 医療施設調査の訪問診療件数から病院ウェイト
- 能力ティア定数の拡張
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MUNICIPAL = PROCESSED / "municipal_home_support_facilities.json"

UA = {"User-Agent": "home-care-target/0.2 (research; accuracy upgrade)"}


def get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s or "")


def parse_num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    x = str(x).strip().replace(",", "")
    if x in ("", "-", "－", "―", "‐", "…"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1) Prefecture home shares from NDB
# ---------------------------------------------------------------------------

def build_prefecture_home_shares(xlsx_path: Path) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["全体"]
    # Row 2 has pref codes 01..47 in columns F onwards? Row 2: 総計, 01, 02...
    # Row 3: 北海道, 青森...
    header_codes = [c.value for c in ws[3]]
    header_names = [c.value for c in ws[4]]
    # columns: 0分類コード 1分類名称 2診療行為コード 3診療行為 4点数 5総計 6..=prefs
    prefs = []
    for i in range(6, len(header_names)):
        name = header_names[i]
        if name:
            prefs.append((i, str(name)))

    # codes of interest
    HOME_CODES = {114001110, 114042110}  # 同一建物以外
    FAC_CODES = {114030310, 114042210, 114042810, 114046310}  # 同一建物 + 訪問診療料2

    totals = {name: {"home": 0.0, "facility": 0.0} for _, name in prefs}
    national = {"home": 0.0, "facility": 0.0}

    for row in ws.iter_rows(min_row=5, values_only=True):
        code = row[2]
        if code is None:
            continue
        try:
            code_i = int(code)
        except (TypeError, ValueError):
            continue
        kind = None
        if code_i in HOME_CODES:
            kind = "home"
        elif code_i in FAC_CODES:
            kind = "facility"
        else:
            continue
        nat = parse_num(row[5]) or 0.0
        national[kind] += nat
        for idx, name in prefs:
            v = parse_num(row[idx]) or 0.0
            totals[name][kind] += v

    out = {
        "source": "第10回NDBオープンデータ C在宅医療 都道府県別算定回数（在宅患者訪問診療料）",
        "as_of": "2023-04〜2024-03",
        "national": {
            "home_claims": national["home"],
            "facility_claims": national["facility"],
            "home_share": national["home"] / max(national["home"] + national["facility"], 1),
        },
        "prefectures": {},
    }
    for name, d in totals.items():
        tot = d["home"] + d["facility"]
        out["prefectures"][name] = {
            "home_claims": d["home"],
            "facility_claims": d["facility"],
            "home_share": (d["home"] / tot) if tot else None,
        }
    return out


# ---------------------------------------------------------------------------
# 2) Hospital weights from e-Stat visit volumes
# ---------------------------------------------------------------------------

def build_hospital_weights(t68: Path, t107: Path) -> dict:
    def load_pref_visit(path: Path, is_hospital: bool) -> dict:
        rows = list(csv.reader(path.open(encoding="utf-8")))
        # First block is 総数 (all hospitals/clinics). Columns after name:
        # for hospital/clinic tables after header rows:
        # r[1]=総数施設? Looking at data: 全国,8122,5144,1791,25546,2904,237601
        # indices: 1=総数(施設?), 2=医療保険総数施設, 3=往診施設, 4=往診件数, 5=訪問診療施設, 6=訪問診療件数
        # Actually from earlier print: ['8122', '5144', '1791', '25546', '2904', '237601', '177']
        # 8122=総数病院, 5144=医療保険等実施施設, then 往診施設1791 件数25546, 訪問診療施設2904 件数237601
        result = {}
        section = "all"
        for r in rows:
            if not r or not r[0].strip():
                continue
            name = clean(r[0])
            # stop before designated-city re-listings (not the table title which also contains 再掲)
            if r[0].strip().startswith("（再掲）"):
                break
            if name in ("総数",) or "第６８表" in r[0] or "第１０７表" in r[0]:
                continue
            # Only take the first occurrence (総合計 block before 精神科/一般病院 split)
            if name in result:
                continue
            # Need enough columns
            if len(r) < 7:
                continue
            facilities = parse_num(r[5])
            claims = parse_num(r[6])
            if facilities is None or claims is None or facilities <= 0:
                continue
            # Map abbreviated names
            pref_map = {
                "全国": "全国",
                "北海道": "北海道",
                "青森": "青森県",
                "岩手": "岩手県",
                "宮城": "宮城県",
                "秋田": "秋田県",
                "山形": "山形県",
                "福島": "福島県",
                "茨城": "茨城県",
                "栃木": "栃木県",
                "群馬": "群馬県",
                "埼玉": "埼玉県",
                "千葉": "千葉県",
                "東京": "東京都",
                "神奈川": "神奈川県",
                "新潟": "新潟県",
                "富山": "富山県",
                "石川": "石川県",
                "福井": "福井県",
                "山梨": "山梨県",
                "長野": "長野県",
                "岐阜": "岐阜県",
                "静岡": "静岡県",
                "愛知": "愛知県",
                "三重": "三重県",
                "滋賀": "滋賀県",
                "京都": "京都府",
                "大阪": "大阪府",
                "兵庫": "兵庫県",
                "奈良": "奈良県",
                "和歌山": "和歌山県",
                "鳥取": "鳥取県",
                "島根": "島根県",
                "岡山": "岡山県",
                "広島": "広島県",
                "山口": "山口県",
                "徳島": "徳島県",
                "香川": "香川県",
                "愛媛": "愛媛県",
                "高知": "高知県",
                "福岡": "福岡県",
                "佐賀": "佐賀県",
                "長崎": "長崎県",
                "熊本": "熊本県",
                "大分": "大分県",
                "宮崎": "宮崎県",
                "鹿児島": "鹿児島県",
                "沖縄": "沖縄県",
            }
            key = pref_map.get(name)
            if not key:
                continue
            result[key] = {
                "visit_facilities": facilities,
                "visit_claims_month": claims,
                "claims_per_facility": claims / facilities,
            }
        return result

    hosp = load_pref_visit(t68, True)
    clin = load_pref_visit(t107, False)
    out = {
        "source": "令和5年医療施設調査 都道府県編 第68表（病院）・第107表（診療所）在宅患者訪問診療 実施件数",
        "as_of": "2023-09",
        "prefectures": {},
    }
    for pref in sorted(set(hosp) | set(clin)):
        h = hosp.get(pref, {})
        c = clin.get(pref, {})
        hw = h.get("claims_per_facility")
        cw = c.get("claims_per_facility")
        weight = (hw / cw) if (hw and cw and cw > 0) else 1.0
        out["prefectures"][pref] = {
            "hospital": h,
            "clinic": c,
            "hospital_weight_vs_clinic": round(weight, 3),
        }
    return out


# ---------------------------------------------------------------------------
# 3) JMAP facility points + GSI geocode
# ---------------------------------------------------------------------------

def scrape_jmap_city(city_code: str, kind: str) -> list[dict]:
    """kind: clinic | hospital"""
    if kind == "clinic":
        typ = "type_zaitaku_clinic:all"
        ftype = "home_support_clinic"
    else:
        typ = "type_zaitaku_hospital:all"
        ftype = "home_support_hospital"
    facilities = []
    page = 1
    while page <= 30:
        url = (
            f"https://jmap.jp/facilities/search/{typ}/"
            f"searchArea:city/searchId:{city_code}/page:{page}"
        )
        html = get(url).decode("utf-8", "replace")
        # Parse table rows with detail link + address
        pattern = re.compile(
            r'<td>([^<]*)</td>\s*'
            r'<td><a href="/facilities/detail/(\d+)">([^<]+)</a></td>\s*'
            r'<td[^>]*>([^<]*)</td>',
            re.S,
        )
        found = 0
        for m in pattern.finditer(html):
            cat, fid, name, addr = m.groups()
            facilities.append(
                {
                    "id": fid,
                    "name": re.sub(r"\s+", " ", name).strip(),
                    "address": addr.strip(),
                    "category": cat.strip(),
                    "facility_type": ftype,
                    "jis_code": city_code,
                }
            )
            found += 1
        # pagination?
        if found == 0:
            break
        if f"/page:{page + 1}" not in html and f"page:{page + 1}" not in html:
            # also check 次へ
            if "次へ" not in html and page > 1:
                break
            if found < 20:
                break
        page += 1
        time.sleep(0.15)
    return facilities


def gsi_geocode(pref: str, address: str) -> tuple[float, float] | None:
    # Prefer full address with prefecture
    q = address if address.startswith(pref) else f"{pref}{address}"
    # Strip building names after numbers roughly
    q = re.split(r"[　\s]+", q)[0]
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?" + urllib.parse.urlencode(
        {"q": q}
    )
    try:
        data = json.loads(get(url, timeout=15).decode("utf-8"))
    except Exception:
        return None
    if not data:
        return None
    coords = data[0]["geometry"]["coordinates"]
    return float(coords[1]), float(coords[0])  # lat, lon


def build_facility_points(municipal: dict, munis_geo: dict) -> dict:
    """Scrape + geocode facilities for municipalities that appear in munis_geo."""
    # Map name -> jis from municipal json
    targets = []
    for name, rec in municipal.items():
        code = rec.get("jis_code")
        if not code or name.endswith("市") and name == "千葉市":
            # use wards instead; skip aggregate
            if name == "千葉市":
                continue
        if code:
            targets.append((name, code))

    # Pref lookup from munis_geo
    pref_of = {n: g["pref"] for n, g in munis_geo.items()}

    all_fac = []
    cache_path = PROCESSED / "geocode_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    for i, (name, code) in enumerate(targets):
        pref = pref_of.get(name, "")
        if not pref:
            # infer
            if name.endswith("区") and not name.startswith("さいたま") and not name.startswith("千葉"):
                pref = "東京都"
            elif name.startswith("さいたま") or name in (
                "所沢市", "入間市", "狭山市", "飯能市", "川越市", "ふじみ野市",
                "新座市", "朝霞市", "志木市", "和光市", "富士見市",
            ):
                pref = "埼玉県"
            elif name.startswith("千葉") or name in (
                "市川市", "船橋市", "松戸市", "野田市", "成田市", "佐倉市", "習志野市",
                "柏市", "市原市", "流山市", "八千代市", "我孫子市", "鎌ケ谷市", "浦安市",
            ):
                pref = "千葉県"
            else:
                pref = "東京都"

        for kind in ("clinic", "hospital"):
            try:
                facs = scrape_jmap_city(code, kind)
            except Exception as e:
                print(f"ERR scrape {name} {kind}: {e}")
                facs = []
            for f in facs:
                f["municipality"] = name
                f["pref"] = pref
                key = f"{pref}|{f['address']}"
                if key in cache:
                    latlon = cache[key]
                else:
                    latlon = gsi_geocode(pref, f["address"])
                    cache[key] = latlon
                    time.sleep(0.05)
                if latlon:
                    f["lat"], f["lon"] = latlon
                    f["geocode"] = "gsi"
                else:
                    # fallback municipality centroid
                    geo = munis_geo.get(name)
                    if geo:
                        f["lat"], f["lon"] = geo["lat"], geo["lon"]
                        f["geocode"] = "municipality_centroid"
                    else:
                        f["lat"] = f["lon"] = None
                        f["geocode"] = "failed"
                all_fac.append(f)
        print(f"[{i+1}/{len(targets)}] {name}: cumulative facilities={len(all_fac)}")
        if (i + 1) % 10 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for f in all_fac if f.get("lat") is not None)
    return {
        "source": "JMAP施設検索 + 国土地理院住所検索API",
        "facility_count": len(all_fac),
        "geocoded_count": ok,
        "facilities": all_fac,
    }


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    # Copy NDB xlsx into raw if present
    for src in (
        Path("/tmp/ndb/ndb_pref_claims.xlsx"),
        Path("/tmp/mhlw_data/t68_hospital_home.csv"),
        Path("/tmp/mhlw_data/t107_clinic_home.csv"),
    ):
        if src.exists():
            dest = RAW / src.name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())

    print("Building prefecture home shares...")
    shares = build_prefecture_home_shares(RAW / "ndb_pref_claims.xlsx")
    (PROCESSED / "prefecture_home_shares.json").write_text(
        json.dumps(shares, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  national home_share", round(shares["national"]["home_share"], 4))
    for p in ("東京都", "埼玉県", "千葉県"):
        print(" ", p, round(shares["prefectures"][p]["home_share"], 4))

    print("Building hospital weights...")
    weights = build_hospital_weights(RAW / "t68_hospital_home.csv", RAW / "t107_clinic_home.csv")
    (PROCESSED / "hospital_visit_weights.json").write_text(
        json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for p in ("全国", "東京都", "埼玉県", "千葉県"):
        w = weights["prefectures"].get(p, {})
        print(" ", p, w.get("hospital_weight_vs_clinic"))

    # Municipality geo from wakasa demo + sibling municipalities for centroids
    from home_care_target.wakasa_demo_data import MUNICIPALITIES

    munis_geo = {
        n: {"lat": m.lat, "lon": m.lon, "pref": m.pref, "area_km2": m.area_km2}
        for n, m in MUNICIPALITIES.items()
    }
    municipal = json.loads(MUNICIPAL.read_text(encoding="utf-8"))

    print("Scraping facility points (this takes a few minutes)...")
    points = build_facility_points(municipal, munis_geo)
    (PROCESSED / "facility_points.json").write_text(
        json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("facilities", points["facility_count"], "geocoded", points["geocoded_count"])

    # Extend capacity constants
    constants = json.loads((PROCESSED / "mhlw_constants.json").read_text(encoding="utf-8"))
    constants["capacity_tiers"] = {
        "standard_mean_total": constants["capacity_benchmarks"]["t108_mean_patients"],
        "active_mean_total": constants["capacity_benchmarks"]["active_mean_patients_ge20"],
        "enhanced_proxy_total": constants["capacity_benchmarks"]["enhanced_proxy_patients"],
        "specialty_p90_total": 150.0,
        "specialty_top_total": 200.0,
        "strategic_home_ratio_default": 0.60,
        "physician_home_per_fte": 100.0,
        "note": "standard/active=一般在支診, specialty=訪問特化・150人超階級",
    }
    constants["overlap"] = {
        "method": "inverse_distance_soft_assignment",
        "group_overlap_radius_km": 16.0,
        "note": "同一グループ院が2R以内にある場合、需要を距離逆数で按分",
    }
    constants["catchment"] = {
        "weight_method": "circle_intersection",
        "note": "市区町村を等面積円で近似し、半径円との交差面積比を重みとする",
    }
    (PROCESSED / "mhlw_constants.json").write_text(
        json.dumps(constants, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Done.")


if __name__ == "__main__":
    # Ensure import path
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    main()
