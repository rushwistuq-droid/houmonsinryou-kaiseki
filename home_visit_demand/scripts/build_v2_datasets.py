#!/usr/bin/env python3
"""高精度推定用データセットを一括生成する。

生成物 (data/processed/):
  - municipalities_age5.json.gz   社人研 市区町村×5歳階級（2025）
  - pref_visit_rates.json         都道府県別訪問診療受療率（NDB）
  - national_visit_rates.json     全国受療率（既存互換＋拡張）
  - mesh_elderly.csv.gz           1/4メッシュ高齢者人口＋座標
  - facilities.csv.gz             入居系事業所（座標・定員推計）
  - national_constants.json       全国定数・補正係数
  - calibration_template.yaml     実績キャリブレーション雛形
"""

from __future__ import annotations

import gzip
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "processed"
OUT.mkdir(parents=True, exist_ok=True)

MESH_ZIPS = Path("/tmp/accuracy/mesh/prefs")
if not MESH_ZIPS.exists() or not any(MESH_ZIPS.glob("*.zip")):
    MESH_ZIPS = DATA / "mesh_zips"
IPSS_DIR = DATA / "ipss_age_raw"
FAC_DIR = DATA / "facilities_raw"

AGE_BANDS_5 = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
    "75-79", "80-84", "85-89", "90+",
]

PREF_NAMES = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県",
}

HOME_CODES = {"114001110", "114042110"}
FACILITY_CODES = {"114030310", "114042210"}
VISIT2_CODES = {"114042810", "114046310"}

FACILITY_FILES = {
    "510": ("介護老人福祉施設", 70.0, 0.944),
    "520": ("介護老人保健施設", 87.0, 0.876),
    "530": ("介護療養型医療施設", 30.0, 0.729),
    "540": ("地域密着型介護老人福祉施設", 29.0, 0.94),
    "550": ("介護医療院", 60.0, 0.912),
    "320": ("認知症対応型共同生活介護", 18.0, 0.95),
    "331": ("特定施設（有料）", 50.0, 0.90),
    "332": ("特定施設（軽費）", 50.0, 0.90),
    "334": ("特定施設（サ高住）", 40.0, 0.90),
    "335": ("特定施設（有料・外部）", 40.0, 0.90),
    "336": ("特定施設（軽費・外部）", 40.0, 0.90),
    "337": ("特定施設（サ高住・外部）", 40.0, 0.90),
    "361": ("地域密着型特定施設（有料）", 29.0, 0.90),
    "362": ("地域密着型特定施設（軽費）", 29.0, 0.90),
    "364": ("地域密着型特定施設（サ高住）", 29.0, 0.90),
}


def _to_float(v) -> float:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    if isinstance(v, str):
        v = v.strip().replace(",", "").replace("*", "")
        if v in {"", "-", "‐", "–", "—", "…", "NaN", "nan"}:
            return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def meshcode_to_latlon(code: str) -> tuple[float, float]:
    """地域メッシュコード（8〜10桁）からメッシュ南西端→中心座標。"""
    code = re.sub(r"\D", "", str(code))
    if len(code) < 8:
        raise ValueError(f"invalid mesh code: {code}")
    # 1次
    lat = int(code[0:2]) * (2.0 / 3.0)
    lon = int(code[2:4]) + 100.0
    # 2次
    lat += int(code[4]) * (2.0 / 3.0) / 8.0
    lon += int(code[5]) / 8.0
    # 3次（約1km）
    lat += int(code[6]) * (2.0 / 3.0) / 8.0 / 10.0
    lon += int(code[7]) / 8.0 / 10.0
    # 中心オフセット（3次メッシュ半幅）
    dlat = (2.0 / 3.0) / 8.0 / 10.0
    dlon = 1.0 / 8.0 / 10.0
    if len(code) >= 9:
        # 1/2メッシュ
        q = int(code[8])
        lat += (q // 2) * (dlat / 2)
        lon += (q % 2) * (dlon / 2)
        dlat /= 2
        dlon /= 2
    if len(code) >= 10:
        # 1/4メッシュ
        q = int(code[9])
        lat += (q // 2) * (dlat / 2)
        lon += (q % 2) * (dlon / 2)
        dlat /= 2
        dlon /= 2
    return lat + dlat / 2, lon + dlon / 2


def build_ipss_municipal_age() -> list[dict]:
    """社人研 市区町村×5歳階級（2025・男女計）。"""
    rows = []
    paths = sorted(IPSS_DIR.glob("*.xlsx"))
    print(f"IPSS files: {len(paths)} from {IPSS_DIR}")
    for path in paths:
        file_pref = path.stem.zfill(2)
        xl = pd.ExcelFile(path)
        for sheet in xl.sheet_names:
            m = re.match(r"^(\d+)_(.+)$", sheet)
            if not m:
                continue
            code, name = m.group(1), m.group(2)
            # 都道府県集計（末尾000）はスキップ
            if code.endswith("000") or re.fullmatch(r"\d{1,2}000", code):
                continue
            # 政令市の市全体（01100等）で区シートがある場合はスキップ
            if re.fullmatch(r"\d{5}", code) and code.endswith("00"):
                prefix3 = code[:3]
                if any(re.match(rf"^{prefix3}[0-9][1-9]_", s) for s in xl.sheet_names):
                    continue

            df = pd.read_excel(xl, sheet_name=sheet, header=None)
            age_map: dict[str, int] = {}
            for i in range(4, min(len(df), 40)):
                raw = df.iloc[i, 0]
                if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                    continue
                label = str(raw).replace(" ", "").replace("　", "").strip()
                val = int(round(_to_float(df.iloc[i, 2])))  # 2025年
                if label == "総数":
                    age_map["total"] = val
                    continue
                if label.startswith("（再掲）") or label.startswith("(再掲)"):
                    continue
                if label.startswith("95"):
                    age_map["90+"] = age_map.get("90+", 0) + val
                    continue
                mm = re.match(r"(\d+)[～〜\-](\d+)歳?", label)
                if not mm:
                    continue
                lo, hi = int(mm.group(1)), int(mm.group(2))
                if lo >= 90:
                    age_map["90+"] = age_map.get("90+", 0) + val
                else:
                    band = f"{lo}-{hi}"
                    age_map[band] = age_map.get(band, 0) + val

            if "total" not in age_map:
                continue

            code5 = code.zfill(5) if len(code) <= 5 else code
            ages_2025 = {b: int(age_map.get(b, 0)) for b in AGE_BANDS_5}
            # 2020列も取得
            age_2020: dict[str, int] = {}
            total_2020 = 0
            for i in range(4, min(len(df), 40)):
                raw = df.iloc[i, 0]
                if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                    continue
                label = str(raw).replace(" ", "").replace("　", "").strip()
                val0 = int(round(_to_float(df.iloc[i, 1])))
                if label == "総数":
                    total_2020 = val0
                    continue
                if label.startswith("（再掲）") or label.startswith("(再掲)"):
                    continue
                if label.startswith("95"):
                    age_2020["90+"] = age_2020.get("90+", 0) + val0
                    continue
                mm = re.match(r"(\d+)[～〜\-](\d+)歳?", label)
                if not mm:
                    continue
                lo, hi = int(mm.group(1)), int(mm.group(2))
                if lo >= 90:
                    age_2020["90+"] = age_2020.get("90+", 0) + val0
                else:
                    age_2020[f"{lo}-{hi}"] = age_2020.get(f"{lo}-{hi}", 0) + val0

            rows.append({
                "code": code5,
                "pref_code": file_pref,
                "pref": PREF_NAMES.get(file_pref, ""),
                "name": name,
                "year": 2025,
                "pop_total": age_map.get("total", 0),
                "pop_total_2020": total_2020,
                "ages": ages_2025,
                "ages_2020": {b: int(age_2020.get(b, 0)) for b in AGE_BANDS_5},
            })

    coords_path = OUT / "municipalities.json"
    coord_map = {}
    if coords_path.exists():
        for muni in json.loads(coords_path.read_text(encoding="utf-8")):
            coord_map[muni["code"]] = (muni["lat"], muni["lon"])
            coord_map[f"{muni['pref']}{muni['name']}"] = (muni["lat"], muni["lon"])
            coord_map[muni["name"]] = (muni["lat"], muni["lon"])
    for r in rows:
        c5 = r["code"][:5]
        if c5 in coord_map:
            r["lat"], r["lon"] = coord_map[c5]
        elif f"{r['pref']}{r['name']}" in coord_map:
            r["lat"], r["lon"] = coord_map[f"{r['pref']}{r['name']}"]
        elif r["name"] in coord_map:
            r["lat"], r["lon"] = coord_map[r["name"]]
        else:
            r["lat"] = r["lon"] = None
    print(f"IPSS municipal age rows: {len(rows)}")
    return rows


def build_rates_from_ndb() -> tuple[dict, dict]:
    """全国・都道府県別の年齢別受療率。"""
    # 全国人口（既存）
    pop2022 = DATA / "pop2022_1.xlsx"
    by_age: dict[int, int] = {}
    dfp = pd.read_excel(pop2022, header=None)

    def parse_age(raw):
        if raw is None or (isinstance(raw, float) and math.isnan(raw)):
            return None
        m = re.search(r"(\d+)", str(raw))
        return int(m.group(1)) if m else None

    for i in range(13, 63):
        for age_col, pop_col in [(0, 1), (9, 10)]:
            a = parse_age(dfp.iloc[i, age_col])
            if a is not None:
                by_age[a] = int(round(_to_float(dfp.iloc[i, pop_col]) * 1000))

    def band_pop(band: str) -> int:
        if band == "90+":
            return sum(v for a, v in by_age.items() if a >= 90)
        lo, hi = map(int, band.split("-"))
        return sum(v for a, v in by_age.items() if lo <= a <= hi)

    pop_bands = {b: band_pop(b) for b in AGE_BANDS_5}

    # 全国年齢別算定
    dfa = pd.read_excel(DATA / "ndb_home_age.xlsx", sheet_name="全体", header=None)
    code_to_idx = {}
    for i in range(4, len(dfa)):
        c = dfa.iloc[i, 2]
        if pd.notna(c):
            code = str(int(c)) if isinstance(c, float) else str(c).strip()
            code_to_idx[code] = i

    def age_counts(row_idx: int):
        male = [_to_float(x) for x in dfa.iloc[row_idx, 6:25].tolist()]
        female = [_to_float(x) for x in dfa.iloc[row_idx, 25:44].tolist()]
        return [m + f for m, f in zip(male, female)]

    home = [0.0] * 19
    fac = [0.0] * 19
    v2 = [0.0] * 19
    for c in HOME_CODES:
        home = [a + b for a, b in zip(home, age_counts(code_to_idx[c]))]
    for c in FACILITY_CODES:
        fac = [a + b for a, b in zip(fac, age_counts(code_to_idx[c]))]
    for c in VISIT2_CODES:
        v2 = [a + b for a, b in zip(v2, age_counts(code_to_idx[c]))]

    claims_per_patient_month = 1.90
    national_bands = {}
    for i, band in enumerate(AGE_BANDS_5):
        annual_home, annual_fac, annual_v2 = home[i], fac[i], v2[i]
        annual_total = annual_home + annual_fac + annual_v2
        pop = max(pop_bands[band], 1)
        patients_total = (annual_total / 12.0) / claims_per_patient_month
        patients_home = (annual_home / 12.0) / claims_per_patient_month
        patients_fac = ((annual_fac + annual_v2) / 12.0) / claims_per_patient_month
        national_bands[band] = {
            "population": pop,
            "patient_rate_total": patients_total / pop,
            "patient_rate_home": patients_home / pop,
            "patient_rate_facility": patients_fac / pop,
            "home_share_of_claims": (annual_home / annual_total) if annual_total else 0.0,
            "annual_claims_total": round(annual_total),
            "annual_claims_home": round(annual_home),
            "annual_claims_facility": round(annual_fac + annual_v2),
        }

    national = {
        "source": {
            "ndb": "第10回NDBオープンデータ（2022年度）C在宅医療",
            "population": "総務省 人口推計 2022年10月1日",
            "claims_per_patient_month": claims_per_patient_month,
        },
        "national_totals": {
            "estimated_monthly_patients_total": round(
                sum(national_bands[b]["patient_rate_total"] * national_bands[b]["population"] for b in AGE_BANDS_5)
            ),
            "estimated_monthly_patients_home": round(
                sum(national_bands[b]["patient_rate_home"] * national_bands[b]["population"] for b in AGE_BANDS_5)
            ),
        },
        "age_bands": national_bands,
        # メッシュ年齢区分用の合成率
        "mesh_band_rates": _mesh_band_rates(national_bands),
    }

    # 都道府県別（年齢なし・全体の居宅/施設シェアと粗受療率）
    dfpref = pd.read_excel(DATA / "ndb_home_pref.xlsx", sheet_name="全体", header=None)
    code_to_idx_p = {}
    for i in range(4, len(dfpref)):
        c = dfpref.iloc[i, 2]
        if pd.notna(c):
            code = str(int(c)) if isinstance(c, float) else str(c).strip()
            code_to_idx_p[code] = i

    # IPSS pref totals for 2025 elderly as denominator proxy — use 2020 census-ish from national scale
    # Better: sum municipal age for each pref from IPSS later; here use claim shares
    pref_rates = {"source": national["source"], "prefectures": {}}
    for pref_i, pref_code in enumerate([f"{i:02d}" for i in range(1, 48)]):
        col = 6 + pref_i  # columns start at 6 for Hokkaido
        def pref_sum(codes):
            s = 0.0
            for c in codes:
                idx = code_to_idx_p.get(c)
                if idx is None:
                    continue
                s += _to_float(dfpref.iloc[idx, col])
            return s
        h = pref_sum(HOME_CODES)
        f = pref_sum(FACILITY_CODES)
        v = pref_sum(VISIT2_CODES)
        total = h + f + v
        pref_rates["prefectures"][pref_code] = {
            "name": PREF_NAMES[pref_code],
            "annual_claims_home": round(h),
            "annual_claims_facility": round(f + v),
            "annual_claims_total": round(total),
            "home_share": (h / total) if total else national_bands["85-89"]["home_share_of_claims"],
            # 年齢別率は全国率×都道府県の総受療水準比で補正（人口は後で掛ける）
            "intensity_vs_national": None,  # filled after municipal pop
        }

    return national, pref_rates


def _mesh_band_rates(bands: dict) -> dict:
    """メッシュの65+/75+/85+/95+区分に合わせた合成受療率。"""
    def wavg(keys, rate_key):
        num = sum(bands[k][rate_key] * bands[k]["population"] for k in keys)
        den = sum(bands[k]["population"] for k in keys) or 1
        return num / den

    return {
        "65-74": {
            "patient_rate_total": wavg(["65-69", "70-74"], "patient_rate_total"),
            "patient_rate_home": wavg(["65-69", "70-74"], "patient_rate_home"),
            "patient_rate_facility": wavg(["65-69", "70-74"], "patient_rate_facility"),
        },
        "75-84": {
            "patient_rate_total": wavg(["75-79", "80-84"], "patient_rate_total"),
            "patient_rate_home": wavg(["75-79", "80-84"], "patient_rate_home"),
            "patient_rate_facility": wavg(["75-79", "80-84"], "patient_rate_facility"),
        },
        "85-94": {
            "patient_rate_total": wavg(["85-89", "90+"], "patient_rate_total") * 0.85,
            "patient_rate_home": wavg(["85-89", "90+"], "patient_rate_home") * 0.85,
            "patient_rate_facility": wavg(["85-89", "90+"], "patient_rate_facility") * 0.85,
        },
        "95+": {
            "patient_rate_total": bands["90+"]["patient_rate_total"] * 1.15,
            "patient_rate_home": bands["90+"]["patient_rate_home"] * 1.15,
            "patient_rate_facility": bands["90+"]["patient_rate_facility"] * 1.15,
        },
    }


def build_mesh_elderly() -> pd.DataFrame:
    """全都道府県メッシュから高齢者人口テーブルを構築。"""
    frames = []
    for zpath in sorted(MESH_ZIPS.glob("*.zip")):
        pref = zpath.stem
        if not re.fullmatch(r"\d{2}", pref):
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                names = [n for n in zf.namelist() if n.endswith(".txt")]
                if not names:
                    continue
                with zf.open(names[0]) as fh:
                    df = pd.read_csv(fh, encoding="cp932", dtype=str, skiprows=[1])
        except Exception as exc:
            print("skip mesh", pref, exc)
            continue
        df = df.rename(columns=str.strip)
        need = {
            "KEY_CODE": "KEY_CODE",
            "T001102001": "pop_total",
            "T001102019": "elderly_65",
            "T001102022": "elderly_75",
            "T001102025": "elderly_85",
            "T001102028": "elderly_95",
        }
        for src, dst in need.items():
            if src not in df.columns:
                raise KeyError(f"{pref}: missing {src}")
        out = pd.DataFrame({
            "mesh_code": df["KEY_CODE"].astype(str).str.replace(r"\D", "", regex=True),
            "pref_code": pref,
            "pop_total": df["T001102001"].map(_to_float),
            "elderly_65": df["T001102019"].map(_to_float),
            "elderly_75": df["T001102022"].map(_to_float),
            "elderly_85": df["T001102025"].map(_to_float),
            "elderly_95": df["T001102028"].map(_to_float),
        })
        # 人口ゼロ・高齢者ゼロ除外
        out = out[(out["pop_total"] > 0) & (out["elderly_65"] > 0)].copy()
        lats, lons = [], []
        for code in out["mesh_code"]:
            try:
                la, lo = meshcode_to_latlon(code)
            except Exception:
                la = lo = float("nan")
            lats.append(la)
            lons.append(lo)
        out["lat"] = lats
        out["lon"] = lons
        out = out.dropna(subset=["lat", "lon"])
        frames.append(out)
        print(f"mesh pref {pref}: {len(out)} cells")
    all_df = pd.concat(frames, ignore_index=True)
    print(f"mesh total cells: {len(all_df)}")
    return all_df


def build_facilities() -> pd.DataFrame:
    rows = []
    for code, (label, default_cap, util) in FACILITY_FILES.items():
        path = FAC_DIR / f"jigyosho_{code}.csv"
        if not path.exists():
            print("missing facility", path)
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "緯度" not in df.columns:
            continue
        for _, r in df.iterrows():
            lat = _to_float(r.get("緯度"))
            lon = _to_float(r.get("経度"))
            if lat == 0 or lon == 0:
                continue
            cap = _to_float(r.get("定員"))
            # 日付が誤入した外れ値・欠損はサービス別中央値で補完
            if cap <= 0 or cap > 500:
                cap = default_cap
            rows.append({
                "service_code": code,
                "service_name": label,
                "name": str(r.get("事業所名", "")),
                "pref": str(r.get("都道府県名", "")),
                "city": str(r.get("市区町村名", "")),
                "lat": lat,
                "lon": lon,
                "capacity": cap,
                "occupancy": util,
                "residents_est": round(cap * util, 1),
            })
    out = pd.DataFrame(rows)
    print(f"facilities: {len(out)}, residents_est sum={out['residents_est'].sum():,.0f}")
    return out


def fill_pref_intensity(pref_rates: dict, munis: list[dict], national: dict) -> dict:
    """都道府県の居宅・施設それぞれの受療強度（全国比）を算出。"""
    elderly_by_pref = defaultdict(float)
    for m in munis:
        ages = m["ages"]
        e = sum(ages.get(b, 0) for b in ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"])
        elderly_by_pref[m["pref_code"]] += e

    nat_home = national["national_totals"]["estimated_monthly_patients_home"]
    nat_total = national["national_totals"]["estimated_monthly_patients_total"]
    nat_fac = nat_total - nat_home
    nat_elderly = sum(
        national["age_bands"][b]["population"]
        for b in ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
    )
    nat_home_rate = nat_home / max(nat_elderly, 1)
    nat_fac_rate = nat_fac / max(nat_elderly, 1)

    for pref_code, info in pref_rates["prefectures"].items():
        e = elderly_by_pref.get(pref_code, 0) or 1
        monthly_home = info["annual_claims_home"] / 12.0 / 1.90
        monthly_fac = info["annual_claims_facility"] / 12.0 / 1.90
        home_intensity = (monthly_home / e) / nat_home_rate if nat_home_rate else 1.0
        fac_intensity = (monthly_fac / e) / nat_fac_rate if nat_fac_rate else 1.0
        # 極端値を抑制（推計の安定性）
        home_intensity = max(0.5, min(1.8, home_intensity))
        fac_intensity = max(0.5, min(2.2, fac_intensity))
        info["elderly_65_2025"] = round(e)
        info["home_intensity_vs_national"] = home_intensity
        info["facility_intensity_vs_national"] = fac_intensity
        info["intensity_vs_national"] = round((home_intensity + fac_intensity) / 2, 3)
        info["age_bands"] = {}
        for band, rb in national["age_bands"].items():
            rh = rb["patient_rate_home"] * home_intensity
            rf = rb["patient_rate_facility"] * fac_intensity
            info["age_bands"][band] = {
                "patient_rate_total": rh + rf,
                "patient_rate_home": rh,
                "patient_rate_facility": rf,
            }
        merged = {
            b: {
                **national["age_bands"][b],
                **info["age_bands"][b],
                "population": national["age_bands"][b]["population"],
            }
            for b in AGE_BANDS_5
        }
        info["mesh_band_rates"] = _mesh_band_rates(merged)
    return pref_rates


def main() -> None:
    print("=== IPSS municipal 5-year age ===")
    munis = build_ipss_municipal_age()
    with gzip.open(OUT / "municipalities_age5.json.gz", "wt", encoding="utf-8") as f:
        json.dump(munis, f, ensure_ascii=False)

    print("=== NDB rates ===")
    national, pref_rates = build_rates_from_ndb()
    pref_rates = fill_pref_intensity(pref_rates, munis, national)
    (OUT / "national_visit_rates.json").write_text(
        json.dumps(national, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "pref_visit_rates.json").write_text(
        json.dumps(pref_rates, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== Mesh elderly ===")
    mesh = build_mesh_elderly()
    mesh.to_csv(OUT / "mesh_elderly.csv.gz", index=False, compression="gzip")

    print("=== Facilities ===")
    fac = build_facilities()
    fac.to_csv(OUT / "facilities.csv.gz", index=False, compression="gzip")

    # 同一建物のうち真の施設比率の補正係数
    # 施設入居者合計 / （施設寄り訪問診療患者の全国推計） から、
    # 「同一建物算定のうち施設由来」の上限を推定
    fac_residents = float(fac["residents_est"].sum())
    fac_patients_nat = (
        national["national_totals"]["estimated_monthly_patients_total"]
        - national["national_totals"]["estimated_monthly_patients_home"]
    )
    facility_visit_rate_among_residents = min(0.85, fac_patients_nat / max(fac_residents, 1))
    # 同一建物算定のうち施設由来。上限0.90とし集合住宅居宅分を残す
    explained = fac_residents * facility_visit_rate_among_residents
    same_building_facility_fraction = min(0.90, max(0.55, explained / max(fac_patients_nat, 1)))

    constants = {
        "source": {
            "mesh": "令和2年国勢調査 地域メッシュ統計 T001102（e-Stat）",
            "ipss": "社人研 地域別将来推計人口（令和5年推計）市区町村5歳階級",
            "ndb": "第10回NDBオープンデータ C在宅医療",
            "facilities": "厚労省 介護サービス情報公表システム オープンデータ",
        },
        "facility_residents_national_est": round(fac_residents),
        "facility_visit_rate_among_residents": facility_visit_rate_among_residents,
        "same_building_facility_fraction": same_building_facility_fraction,
        "apartment_same_building_fraction": 1.0 - same_building_facility_fraction,
        "claims_per_patient_month": 1.90,
        "mesh_year": 2020,
        "population_projection_year": 2025,
        "social_medical_stats_patients_2023_06": 1001102,
    }
    pop_bands = {b: national["age_bands"][b]["population"] for b in AGE_BANDS_5}
    e65 = sum(pop_bands[b] for b in ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"])
    e75 = sum(pop_bands[b] for b in ["75-79", "80-84", "85-89", "90+"])
    e6574 = pop_bands["65-69"] + pop_bands["70-74"]
    constants.update({
        "facility_residents_per_elderly_65": fac_residents / max(e65, 1),
        "national_elderly_65_2022": e65,
        "national_elderly_75_2022": e75,
        "share_within_65_74": {
            "65-69": pop_bands["65-69"] / max(e6574, 1),
            "70-74": pop_bands["70-74"] / max(e6574, 1),
        },
        "share_within_75plus": {
            "75-79": pop_bands["75-79"] / max(e75, 1),
            "80-84": pop_bands["80-84"] / max(e75, 1),
            "85-89": pop_bands["85-89"] / max(e75, 1),
            "90+": pop_bands["90+"] / max(e75, 1),
        },
        "care_insurance_facility_residents_est": round(fac_residents * 0.65),
        "national_visit_patients_2023_06": 1001102,
        "visit_patients_per_elderly_65": 1001102 / max(e65, 1),
    })
    (OUT / "national_constants.json").write_text(
        json.dumps(constants, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    calib = """# 実績キャリブレーション用テンプレート
# 各クリニックの居宅・施設患者数実績を入れると、推計との比で補正係数を算出します。
#
# estimated_home = model_home * calibration_factor
# calibration_factor は実績がある院の (actual_home / model_home) の縮小推定平均

meta:
  as_of: "2026-07"
  notes: "本部検証用。実績は機密のため本ファイルは gitignore 推奨。"

clinics: []
# 例:
# - id: "tokorozawa"
#   name: "わかさクリニック所沢"
#   address: "埼玉県所沢市くすのき台3-4-4"
#   lat: 35.799
#   lon: 139.472
#   actual_home_patients: 120
#   actual_facility_patients: 80
#   physicians_fte: 2.0
"""
    (OUT / "calibration_template.yaml").write_text(calib, encoding="utf-8")
    print("done ->", OUT)


if __name__ == "__main__":
    main()
