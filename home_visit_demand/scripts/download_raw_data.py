#!/usr/bin/env python3
"""高精度推定用の原本統計をダウンロードする。"""
from __future__ import annotations
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FAC_CODES = ["320","331","332","334","335","336","337","361","362","364","510","520","530","540","550"]

def get(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("GET", url, "->", dest)
    urllib.request.urlretrieve(url, dest)

def main():
    # IPSS
    ipss = DATA / "ipss_age_raw"
    for i in range(1, 48):
        code = f"{i:02d}"
        get(f"https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities/{code}.xlsx", ipss / f"{code}.xlsx")
    # Mesh
    mesh = DATA / "mesh_zips"
    for i in range(1, 48):
        code = f"{i:02d}"
        get(f"https://www.e-stat.go.jp/gis/statmap-search/data?statsId=T001102&code={code}&coordsys=1&format=shape&downloadType=2", mesh / f"{code}.zip")
    # Facilities
    fac = DATA / "facilities_raw"
    for c in FAC_CODES:
        get(f"https://www.mhlw.go.jp/content/12300000/jigyosho_{c}.csv", fac / f"jigyosho_{c}.csv")
    # NDB
    get("https://www.mhlw.go.jp/content/12400000/001258288.xlsx", DATA / "ndb_home_age.xlsx")
    get("https://www.mhlw.go.jp/content/12400000/001258289.xlsx", DATA / "ndb_home_pref.xlsx")
    print("done. next: python3 scripts/build_v2_datasets.py")

if __name__ == "__main__":
    main()
