#!/usr/bin/env python3
"""公的統計から推定用データセットを生成する。

入力（data/ 配下の原本）:
  - ndb_home_age.xlsx … 第10回 NDBオープンデータ C在宅医療 性年齢別算定回数
  - pop2022_1.xlsx … 総務省 人口推計 2022年10月1日 年齢別人口
  - kekkahyo1/2_3/2_4.xlsx … 社人研 地域別将来推計人口（令和5年推計）
  - munic_coords.json … Wikidata（JIS市区町村コード + 座標）
  - kaigo_data05.xlsx … 厚労省 介護サービス施設・事業所調査 令和5年 概況

出力（data/processed/）:
  - national_visit_rates.json
  - municipalities.json
  - national_constants.json
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "processed"
OUT.mkdir(parents=True, exist_ok=True)

AGE_BANDS = [
    "0-4",
    "5-9",
    "10-14",
    "15-19",
    "20-24",
    "25-29",
    "30-34",
    "35-39",
    "40-44",
    "45-49",
    "50-54",
    "55-59",
    "60-64",
    "65-69",
    "70-74",
    "75-79",
    "80-84",
    "85-89",
    "90+",
]

# 在宅患者訪問診療料の診療行為コード
HOME_CODES = {"114001110", "114042110"}  # 同一建物以外
FACILITY_CODES = {"114030310", "114042210"}  # 同一建物
VISIT2_CODES = {"114042810", "114046310"}  # 訪問診療料（２）


def _to_float(v) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    if isinstance(v, str):
        v = v.strip().replace(",", "")
        if v in {"", "-", "‐", "–", "—", "…", "*"}:
            return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_national_population() -> dict[str, int]:
    """総務省人口推計（千人）→ 人数。"""
    df = pd.read_excel(DATA / "pop2022_1.xlsx", header=None)
    by_age: dict[int, int] = {}

    def parse_age(raw) -> int | None:
        if raw is None or (isinstance(raw, float) and math.isnan(raw)):
            return None
        s = str(raw)
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else None

    for i in range(13, 63):
        age_l = parse_age(df.iloc[i, 0])
        pop_l = _to_float(df.iloc[i, 1])
        age_r = parse_age(df.iloc[i, 9])
        pop_r = _to_float(df.iloc[i, 10])
        if age_l is not None:
            by_age[age_l] = int(round(pop_l * 1000))
        if age_r is not None:
            by_age[age_r] = int(round(pop_r * 1000))

    # 100歳以上は右列の続きにない場合があるので合計整合は近似
    bands: dict[str, int] = {}
    for band in AGE_BANDS:
        if band == "90+":
            bands[band] = sum(v for a, v in by_age.items() if a >= 90)
        else:
            lo, hi = map(int, band.split("-"))
            bands[band] = sum(v for a, v in by_age.items() if lo <= a <= hi)
    return bands


def build_visit_rates(pop_bands: dict[str, int]) -> dict:
    df = pd.read_excel(DATA / "ndb_home_age.xlsx", sheet_name="全体", header=None)
    code_to_idx: dict[str, int] = {}
    for i in range(4, len(df)):
        c = df.iloc[i, 2]
        if pd.notna(c):
            code = str(int(c)) if isinstance(c, float) else str(c).strip()
            code_to_idx[code] = i

    def age_counts(row_idx: int):
        male = [_to_float(x) for x in df.iloc[row_idx, 6:25].tolist()]
        female = [_to_float(x) for x in df.iloc[row_idx, 25:44].tolist()]
        return [m + f for m, f in zip(male, female)]

    home = [0.0] * 19
    facility = [0.0] * 19
    visit2 = [0.0] * 19
    for code in HOME_CODES:
        vals = age_counts(code_to_idx[code])
        home = [a + b for a, b in zip(home, vals)]
    for code in FACILITY_CODES:
        vals = age_counts(code_to_idx[code])
        facility = [a + b for a, b in zip(facility, vals)]
    for code in VISIT2_CODES:
        vals = age_counts(code_to_idx[code])
        visit2 = [a + b for a, b in zip(visit2, vals)]

    # 社会医療診療行為別統計: 月あたり算定回数 / 患者 ≈ 1.90
    claims_per_patient_month = 1.90

    bands = {}
    for i, band in enumerate(AGE_BANDS):
        annual_home = home[i]
        annual_fac = facility[i]
        annual_v2 = visit2[i]
        annual_total = annual_home + annual_fac + annual_v2
        monthly_total = annual_total / 12.0
        monthly_home = annual_home / 12.0
        monthly_fac = (annual_fac + annual_v2) / 12.0  # 施設寄りに（２）を含める
        pop = max(pop_bands[band], 1)
        patients_total = monthly_total / claims_per_patient_month
        patients_home = monthly_home / claims_per_patient_month
        patients_fac = monthly_fac / claims_per_patient_month
        bands[band] = {
            "population": pop,
            "annual_claims_home": round(annual_home),
            "annual_claims_facility": round(annual_fac),
            "annual_claims_visit2": round(annual_v2),
            "annual_claims_total": round(annual_total),
            "patient_rate_total": patients_total / pop,
            "patient_rate_home": patients_home / pop,
            "patient_rate_facility": patients_fac / pop,
            "home_share_of_claims": (annual_home / annual_total) if annual_total else 0.0,
        }

    # 検証: 全国合計患者数
    total_patients = sum(
        bands[b]["patient_rate_total"] * bands[b]["population"] for b in AGE_BANDS
    )
    home_patients = sum(
        bands[b]["patient_rate_home"] * bands[b]["population"] for b in AGE_BANDS
    )

    return {
        "source": {
            "ndb": "第10回NDBオープンデータ（診療年月:2022年4月〜2023年3月）C在宅医療 性年齢別算定回数",
            "population": "総務省統計局 人口推計（2022年10月1日現在）年齢各歳別人口",
            "claims_per_patient_month": claims_per_patient_month,
            "claims_per_patient_note": "社会医療診療行為別統計（在宅患者訪問診療料の算定回数÷算定患者）に近似した係数1.90",
        },
        "national_totals": {
            "estimated_monthly_patients_total": round(total_patients),
            "estimated_monthly_patients_home": round(home_patients),
            "estimated_monthly_patients_facility": round(total_patients - home_patients),
        },
        "age_bands": bands,
    }


def build_national_constants() -> dict:
    # 介護保険施設定員（令和5年10月1日）
    beds = {
        "介護老人福祉施設": 597973,
        "介護老人保健施設": 369365,
        "介護医療院": 46970,
        "介護療養型医療施設": 6052,
    }
    total_beds = sum(beds.values())
    # 利用率（詳細票・令和5年9月末）
    util = {
        "介護老人福祉施設": 0.944,
        "介護老人保健施設": 0.876,
        "介護医療院": 0.912,
        "介護療養型医療施設": 0.729,
    }
    care_insurance_residents = sum(beds[k] * util[k] for k in beds)

    # 入居系の広義推計（介護保険施設 + 特定施設・GH等）
    # 特定施設・認知症GHの利用者規模は厚労省公表の概数を使用
    # （厳密な定員統計が概況表に無いため、公的資料ベースの概数）
    broader_extra_residents = {
        "特定施設入居者生活介護_利用者概数": 270000,
        "認知症対応型共同生活介護_利用者概数": 210000,
    }
    residents = care_insurance_residents + sum(broader_extra_residents.values())

    # 65歳以上人口（2022年10月）
    pop = build_national_population()
    elderly_65 = (
        pop["65-69"]
        + pop["70-74"]
        + pop["75-79"]
        + pop["80-84"]
        + pop["85-89"]
        + pop["90+"]
    )
    elderly_75 = pop["75-79"] + pop["80-84"] + pop["85-89"] + pop["90+"]

    # 社会医療診療行為別統計 2023年6月審査分
    social_stats_patients = 1001102

    return {
        "source": {
            "care_facilities": "厚生労働省 令和5年介護サービス施設・事業所調査 概況（定員・利用率）＋特定施設・GH利用者の公的概数",
            "social_medical_stats": "厚生労働省 2023年社会医療診療行為別統計（在宅患者訪問診療料・月1回以上算定患者）",
        },
        "care_insurance_facility_beds_2023": beds,
        "care_insurance_facility_beds_total": total_beds,
        "care_insurance_facility_residents_est": round(care_insurance_residents),
        "broader_extra_residents": broader_extra_residents,
        "residential_facility_residents_est": round(residents),
        "facility_residents_per_elderly_65": residents / elderly_65,
        "facility_residents_per_elderly_75": residents / elderly_75,
        "national_visit_patients_2023_06": social_stats_patients,
        "national_elderly_65_2022": elderly_65,
        "national_elderly_75_2022": elderly_75,
        "visit_patients_per_elderly_65": social_stats_patients / elderly_65,
        # 75+内訳シェア（全国年齢構造）。市区町村の75+を細分化する際に使用
        "share_within_75plus": {
            "75-79": pop["75-79"] / elderly_75,
            "80-84": pop["80-84"] / elderly_75,
            "85-89": pop["85-89"] / elderly_75,
            "90+": pop["90+"] / elderly_75,
        },
        "share_within_65_74": {
            "65-69": pop["65-69"] / (pop["65-69"] + pop["70-74"]),
            "70-74": pop["70-74"] / (pop["65-69"] + pop["70-74"]),
        },
    }


def _norm_name(name: str) -> str:
    return (
        str(name)
        .replace(" ", "")
        .replace("　", "")
        .replace("ヶ", "ケ")
        .replace("ヵ", "カ")
    )


def build_municipalities() -> list[dict]:
    # IPSS population
    total = pd.read_excel(DATA / "kekkahyo1.xlsx", header=None)
    e65 = pd.read_excel(DATA / "kekkahyo2_3.xlsx", header=None)
    e75 = pd.read_excel(DATA / "kekkahyo2_4.xlsx", header=None)

    def load_ipss(df) -> dict[str, dict]:
        out = {}
        for i in range(5, len(df)):
            code = df.iloc[i, 0]
            kind = df.iloc[i, 1]
            pref = df.iloc[i, 2]
            name = df.iloc[i, 3]
            if pd.isna(code) or pd.isna(kind):
                continue
            # 都道府県集計・政令市合計はスキップ（区単位を使う）
            kind_s = str(kind).strip()
            if kind_s in {"a", "1"}:
                continue
            if pd.isna(name) or str(name).strip() == "":
                continue
            code_s = str(int(code)) if isinstance(code, float) else str(code).strip()
            # 2025年列 = index 5
            pop_2025 = int(_to_float(df.iloc[i, 5]))
            pop_2020 = int(_to_float(df.iloc[i, 4]))
            out[code_s] = {
                "code": code_s.zfill(5) if len(code_s) <= 5 else code_s,
                "kind": kind_s,
                "pref": str(pref).strip(),
                "name": str(name).strip(),
                "value_2020": pop_2020,
                "value_2025": pop_2025,
            }
        return out

    tot_map = load_ipss(total)
    e65_map = load_ipss(e65)
    e75_map = load_ipss(e75)

    # Coordinates from Wikidata
    coords_raw = json.loads((DATA / "munic_coords.json").read_text(encoding="utf-8"))
    by_code: dict[str, list] = defaultdict(list)
    by_name: dict[str, list] = defaultdict(list)
    for b in coords_raw["results"]["bindings"]:
        code = b["code"]["value"].zfill(6) if len(b["code"]["value"]) <= 6 else b["code"]["value"]
        # JIS市区町村コードは5桁が一般的。Wikidataは6桁（末尾チェックディジットなしの場合あり）
        code5 = code[:5]
        name = b["name"]["value"]
        lat = float(b["lat"]["value"])
        lon = float(b["lon"]["value"])
        by_code[code5].append((lat, lon, name))
        by_name[_norm_name(name)].append((lat, lon, code5, name))

    municipalities = []
    missing_coords = 0
    for code, row in tot_map.items():
        code5 = code.zfill(5)[:5]
        e65 = e65_map.get(code, {})
        e75 = e75_map.get(code, {})
        elderly_65 = e65.get("value_2025", 0)
        elderly_75 = e75.get("value_2025", 0)
        name = row["name"]
        pref = row["pref"]

        lat = lon = None
        # Prefer exact code match
        if code5 in by_code:
            # average if duplicates
            pts = by_code[code5]
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
        else:
            # name match within same pref is hard without pref on coords; try unique name
            cands = by_name.get(_norm_name(name), [])
            if len(cands) == 1:
                lat, lon = cands[0][0], cands[0][1]
            elif cands:
                # pick first; imperfect but rare
                lat, lon = cands[0][0], cands[0][1]

        if lat is None:
            missing_coords += 1
            continue

        municipalities.append(
            {
                "code": code5,
                "pref": pref,
                "name": name,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "pop_total_2025": row["value_2025"],
                "elderly_65_2025": elderly_65,
                "elderly_75_2025": elderly_75,
                "elderly_65_74_2025": max(0, elderly_65 - elderly_75),
            }
        )

    print(f"municipalities with coords: {len(municipalities)}, missing: {missing_coords}")
    return municipalities


def main() -> None:
    pop_bands = build_national_population()
    rates = build_visit_rates(pop_bands)
    constants = build_national_constants()
    munis = build_municipalities()

    (OUT / "national_visit_rates.json").write_text(
        json.dumps(rates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "national_constants.json").write_text(
        json.dumps(constants, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "municipalities.json").write_text(
        json.dumps(munis, ensure_ascii=False), encoding="utf-8"
    )

    print("national patients est:", rates["national_totals"])
    print("facility residents/elderly65:", round(constants["facility_residents_per_elderly_65"], 4))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
