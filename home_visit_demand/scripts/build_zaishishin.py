#!/usr/bin/env python3
"""関東信越厚生局の届出受理名簿から在宅療養支援診療所を抽出し座標付与する。"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "zaishishin_raw"
OUT = ROOT / "data" / "processed"
CLINIC_FACILITY = (
    ROOT
    / "data"
    / "clinics_raw"
    / "extracted_facility"
    / "02-1_clinic_facility_info_20251201.csv"
)

ZIP_URL = "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/shisetsu_ika_r0807.zip"
# わかさ圏域に必要な都県（必要なら神奈川も）
TARGET_PREFS = ("11", "12", "13", "14")  # 埼玉・千葉・東京・神奈川

ZAISHI_RE = re.compile(r"在宅療養支援診療所")
ZAIBYO_RE = re.compile(r"在宅療養支援病院")


def _norm_name(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"[\s　]+", "", s)
    for a in (
        "医療法人社団",
        "医療法人財団",
        "社会医療法人社団",
        "社会医療法人",
        "医療法人",
        "株式会社",
        "有限会社",
        "一般社団法人",
        "社会福祉法人",
    ):
        s = s.replace(a, "")
    return s


def _norm_postal(s: str) -> str:
    s = str(s or "")
    s = s.replace("〒", "")
    s = re.sub(r"[‐－—–−]", "-", s)
    s = re.sub(r"[^0-9]", "", s)
    return s


def _norm_addr(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"[\s　]+", "", s)
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    s = re.sub(r"[‐－—–−]", "-", s)
    return s


def download_zip(force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "shisetsu_ika_r0807.zip"
    if force or not dest.exists():
        print(f"downloading {ZIP_URL}", flush=True)
        urlretrieve(ZIP_URL, dest)
    with zipfile.ZipFile(dest) as zf:
        zf.extractall(RAW)
    return dest


def load_zaishi_from_excels() -> pd.DataFrame:
    rows = []
    base = RAW / "shisetsu_ika_r0807"
    for path in sorted(base.glob("*.xlsx")):
        code = path.name[:2]
        if code not in TARGET_PREFS:
            continue
        print(f"reading {path.name} ...", flush=True)
        df = pd.read_excel(path, header=3)
        name_col = "受理届出名称"
        m = df[name_col].astype(str).str.contains(ZAISHI_RE)
        sub = df.loc[m].copy()
        if sub.empty:
            continue
        sub["pref_code"] = code
        sub["kind"] = "在宅療養支援診療所"
        # 機能区分
        sub["zaishi_class"] = sub["受理記号"].astype(str)
        rows.append(sub)
        # 病院も参考抽出
        m2 = df[name_col].astype(str).str.contains(ZAIBYO_RE)
        if m2.any():
            h = df.loc[m2].copy()
            h["pref_code"] = code
            h["kind"] = "在宅療養支援病院"
            h["zaishi_class"] = h["受理記号"].astype(str)
            rows.append(h)
    if not rows:
        raise RuntimeError("在支診行が見つかりません")
    all_df = pd.concat(rows, ignore_index=True)
    # 機関単位で一意（複数区分がある場合は記号を結合）
    all_df["postal"] = all_df["医療機関所在地（郵便番号）"].map(_norm_postal)
    all_df["name_norm"] = all_df["医療機関名称"].map(_norm_name)
    all_df["addr_norm"] = all_df["医療機関所在地（住所）"].map(_norm_addr)

    def agg_class(s: pd.Series) -> str:
        return "|".join(sorted({str(x) for x in s if str(x) and str(x) != "nan"}))

    clinics = (
        all_df.groupby(["pref_code", "医療機関番号", "kind"], as_index=False)
        .agg(
            {
                "都道府県名": "first",
                "医療機関名称": "first",
                "医療機関所在地（郵便番号）": "first",
                "医療機関所在地（住所）": "first",
                "postal": "first",
                "name_norm": "first",
                "addr_norm": "first",
                "zaishi_class": agg_class,
                "受理届出名称": "first",
            }
        )
        .rename(
            columns={
                "医療機関番号": "medical_code",
                "都道府県名": "pref_name",
                "医療機関名称": "name",
                "医療機関所在地（郵便番号）": "postal_raw",
                "医療機関所在地（住所）": "address",
                "受理届出名称": "acceptance_name",
            }
        )
    )
    return clinics


def load_clinic_coords() -> pd.DataFrame:
    if not CLINIC_FACILITY.exists():
        # build competitors first may have created it; try rebuild path
        raise FileNotFoundError(
            f"{CLINIC_FACILITY} がありません。先に scripts/build_competitors.py を実行してください。"
        )
    fac = pd.read_csv(
        CLINIC_FACILITY,
        encoding="utf-8-sig",
        usecols=[
            "ID",
            "正式名称",
            "所在地",
            "都道府県コード",
            "所在地座標（緯度）",
            "所在地座標（経度）",
        ],
        dtype={"ID": str, "都道府県コード": str},
    )
    fac["lat"] = pd.to_numeric(fac["所在地座標（緯度）"], errors="coerce")
    fac["lon"] = pd.to_numeric(fac["所在地座標（経度）"], errors="coerce")
    fac = fac[fac["lat"].between(20, 50) & fac["lon"].between(120, 150)].copy()
    fac["name_norm"] = fac["正式名称"].map(_norm_name)
    fac["addr_norm"] = fac["所在地"].map(_norm_addr)
    fac["pref_code"] = fac["都道府県コード"].astype(str).str.zfill(2)
    return fac


def attach_coords(zaishi: pd.DataFrame, fac: pd.DataFrame) -> pd.DataFrame:
    """名称（同一都県）→ 住所部分一致の順で座標付与。"""
    out_rows = []
    fac_by_pref = {p: g for p, g in fac.groupby("pref_code")}
    matched = 0
    for r in zaishi.itertuples(index=False):
        lat = lon = None
        match_how = ""
        facility_id = ""
        g = fac_by_pref.get(str(r.pref_code), fac.iloc[0:0])
        # 1) exact normalized name in pref
        hits = g[g["name_norm"] == r.name_norm]
        if len(hits) >= 1:
            best_row = hits.iloc[0]
            if r.addr_norm and len(hits) > 1:
                best_score = -1
                for _, h in hits.iterrows():
                    score = 0
                    addr = str(h["addr_norm"])
                    if r.addr_norm[:6] and r.addr_norm[:6] in addr:
                        score += 2
                    if addr[:8] and addr[:8] in r.addr_norm:
                        score += 1
                    if score > best_score:
                        best_score = score
                        best_row = h
            lat, lon = float(best_row["lat"]), float(best_row["lon"])
            facility_id = str(best_row["ID"])
            match_how = "name"
            matched += 1
        else:
            # 2) address contains
            if r.addr_norm and len(r.addr_norm) >= 8:
                key = r.addr_norm[:10]
                hits2 = g[g["addr_norm"].str.contains(re.escape(key), na=False)]
                if len(hits2) == 1:
                    best_row = hits2.iloc[0]
                    lat, lon = float(best_row["lat"]), float(best_row["lon"])
                    facility_id = str(best_row["ID"])
                    match_how = "address"
                    matched += 1
        out_rows.append(
            {
                "medical_code": r.medical_code,
                "pref_code": r.pref_code,
                "pref_name": r.pref_name,
                "name": r.name,
                "postal": r.postal,
                "address": r.address,
                "kind": r.kind,
                "zaishi_class": r.zaishi_class,
                "acceptance_name": r.acceptance_name,
                "lat": lat,
                "lon": lon,
                "match_how": match_how,
                "facility_id": facility_id,
                "source": "関東信越厚生局 届出受理医療機関名簿（医科）R8.6.1現在",
            }
        )
    out = pd.DataFrame(out_rows)
    print(
        f"coords matched {matched}/{len(out)} ({100*matched/len(out):.1f}%)",
        flush=True,
    )
    return out


def build(force_download: bool = False) -> Path:
    download_zip(force=force_download)
    zaishi = load_zaishi_from_excels()
    print(
        "extracted",
        len(zaishi),
        "institutions; clinics",
        int((zaishi.kind == "在宅療養支援診療所").sum()),
        "hospitals",
        int((zaishi.kind == "在宅療養支援病院").sum()),
    )
    fac = load_clinic_coords()
    out = attach_coords(zaishi, fac)
    # 診療所のみを主競合に、病院は別フラグ
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "zaishishin.csv.gz"
    out.to_csv(path, index=False, compression="gzip")
    meta = {
        "source": "関東信越厚生局 保険医療機関の施設基準 届出受理医療機関名簿（医科）",
        "source_url": "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/chousa/kijyun.html",
        "as_of": "2026-06-01",
        "prefs": list(TARGET_PREFS),
        "total": int(len(out)),
        "zaishishin_clinics": int((out.kind == "在宅療養支援診療所").sum()),
        "zaishishin_hospitals": int((out.kind == "在宅療養支援病院").sum()),
        "with_coords": int(out.lat.notna().sum()),
        "coord_match_rate": round(float(out.lat.notna().mean()), 3),
        "note": "座標は医療情報ネット公開診療所との名称・住所突合。未突合は半径集計から除外。",
    }
    meta_path = OUT / "zaishishin_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")
    print(f"wrote {meta_path}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--force-download", action="store_true")
    args = p.parse_args()
    build(force_download=args.force_download)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
