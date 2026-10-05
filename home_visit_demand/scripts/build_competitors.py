#!/usr/bin/env python3
"""医療情報ネット公開データから訪問診療競合ポイントを加工する。"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "clinics_raw"
OUT = ROOT / "data" / "processed"

CLINIC_FACILITY_URL = (
    "https://www.mhlw.go.jp/content/11121000/02-1_clinic_facility_info_20251201.zip"
)
CLINIC_SPEC_URL = (
    "https://www.mhlw.go.jp/content/11121000/02-2_clinic_speciality_hours_20251201.zip"
)

HOME_NAME_RE = re.compile(r"在宅|訪問診療|ホームケア|訪問クリニック|在宅医療")
HOME_SPEC_RE = re.compile(r"在宅|訪問診療|往診")


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print(f"downloading {url} ...", flush=True)
        urlretrieve(url, dest)
    return dest


def _unzip(zip_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
        names = zf.namelist()
    csvs = list(out_dir.rglob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"no csv in {zip_path}")
    return csvs[0]


def build(force_download: bool = False) -> dict[str, Path]:
    if force_download:
        for p in [
            RAW / "clinic_facility_20251201.zip",
            RAW / "clinic_specialty_20251201.zip",
        ]:
            if p.exists():
                p.unlink()

    fac_zip = _download(CLINIC_FACILITY_URL, RAW / "clinic_facility_20251201.zip")
    spec_zip = _download(CLINIC_SPEC_URL, RAW / "clinic_specialty_20251201.zip")
    fac_csv = _unzip(fac_zip, RAW / "extracted_facility")
    spec_csv = _unzip(spec_zip, RAW / "extracted_specialty")

    fac = pd.read_csv(
        fac_csv,
        encoding="utf-8-sig",
        usecols=[
            "ID",
            "正式名称",
            "所在地",
            "都道府県コード",
            "市区町村コード",
            "所在地座標（緯度）",
            "所在地座標（経度）",
        ],
        dtype={"ID": str, "都道府県コード": str, "市区町村コード": str},
    )
    fac = fac.rename(
        columns={
            "正式名称": "name",
            "所在地": "address",
            "都道府県コード": "pref_code",
            "市区町村コード": "city_code",
            "所在地座標（緯度）": "lat",
            "所在地座標（経度）": "lon",
        }
    )
    fac["lat"] = pd.to_numeric(fac["lat"], errors="coerce")
    fac["lon"] = pd.to_numeric(fac["lon"], errors="coerce")
    valid = (
        fac["lat"].between(20, 50)
        & fac["lon"].between(120, 150)
    )
    fac_v = fac.loc[valid].copy()

    spec = pd.read_csv(
        spec_csv,
        encoding="utf-8-sig",
        usecols=["ID", "診療科目名"],
        dtype={"ID": str},
    )
    home_spec_ids = set(
        spec.loc[
            spec["診療科目名"].fillna("").map(lambda x: bool(HOME_SPEC_RE.search(str(x)))),
            "ID",
        ]
    )
    fac_v["name_home"] = fac_v["name"].fillna("").map(lambda x: bool(HOME_NAME_RE.search(str(x))))
    fac_v["spec_home"] = fac_v["ID"].isin(home_spec_ids)
    fac_v["is_home_competitor"] = fac_v["name_home"] | fac_v["spec_home"]

    # 全診療所座標（密度用・軽量）
    all_coords = fac_v[["ID", "lat", "lon", "pref_code"]].copy()
    all_coords["kind"] = "clinic"

    # 訪問診療寄り競合
    home = fac_v.loc[
        fac_v["is_home_competitor"],
        ["ID", "name", "address", "pref_code", "city_code", "lat", "lon", "name_home", "spec_home"],
    ].copy()
    home["kind"] = "home_visit_clinic"
    home["source"] = "mhlw_iryou_joho_net_20251201"

    OUT.mkdir(parents=True, exist_ok=True)
    all_path = OUT / "clinics_all_coords.csv.gz"
    home_path = OUT / "competitors_home.csv.gz"
    meta_path = OUT / "competitors_meta.json"

    all_coords.to_csv(all_path, index=False, compression="gzip")
    home.to_csv(home_path, index=False, compression="gzip")

    import json

    meta = {
        "source": "厚生労働省 医療情報ネット オープンデータ（診療所施設票・診療科票）2025-12-01",
        "source_url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html",
        "clinic_total_with_coords": int(len(fac_v)),
        "home_competitors": int(len(home)),
        "home_filter": "名称に在宅|訪問診療等、または診療科目に在宅|訪問診療|往診",
        "note": "在宅療養支援診療所の全件フラグは本オープンデータに含まれないため、名称・科目による近似。",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {all_path} ({len(all_coords)} rows)")
    print(f"wrote {home_path} ({len(home)} rows)")
    print(f"wrote {meta_path}")
    return {"all": all_path, "home": home_path, "meta": meta_path}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--force-download", action="store_true")
    args = p.parse_args()
    build(force_download=args.force_download)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
