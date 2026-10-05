#!/usr/bin/env python3
"""追加の公開データを取得・整形する（要ネット接続）。

    python3 briefing/scripts/build_extra_datasets.py            # 取得＋整形
    python3 briefing/scripts/build_extra_datasets.py --no-fetch # 取得済みファイルから整形のみ

出力（briefing/data/processed/）:
  cm_offices.csv.gz        居宅介護支援事業所（CM）  介護サービス情報公表 オープンデータ（jigyosho_430）
  nursing_stations.csv.gz  訪問看護ステーション       同（jigyosho_130）
  future_pop.csv.gz        市区町村別 65/75/85歳以上 2020〜2050年  社人研 令和5年推計
  zaishishin_gsi.json      座標が無い在支診・在支病を国土地理院 住所検索で補完した結果（キャッシュ）
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_FAC = ROOT / "home_visit_demand/data/facilities_raw"
RAW_IPSS = ROOT / "home_visit_demand/data/ipss_age_raw"
OUT = ROOT / "briefing/data/processed"
PREFS = ["08", "09", "10", "11", "12", "13", "14", "19"]  # 1都3県＋隣接県
PREF_NAMES = ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "山梨県"]
FAC_URL = "https://www.mhlw.go.jp/content/12300000/jigyosho_{code}.csv"
IPSS_URL = "https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities/{code}.xlsx"
GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="
YEARS = [2020, 2025, 2030, 2035, 2040, 2045, 2050]
# 政令指定都市・特別区部の「市全体」シート。区のシートと二重計上になるため除外する
CITY_TOTAL_CODES = {"11100", "12100", "13100", "14100", "14130", "14150"}


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("GET", url)
    urllib.request.urlretrieve(url, dest)


def build_offices(code: str, out_name: str) -> None:
    df = pd.read_csv(RAW_FAC / f"jigyosho_{code}.csv", encoding="utf-8-sig", dtype=str)
    df = df[df["都道府県名"].isin(PREF_NAMES)]
    out = pd.DataFrame(
        {
            "office_no": df["事業所番号"],
            "name": df["事業所名"],
            "corp": df["法人の名称"],
            "pref": df["都道府県名"],
            "city": df["市区町村名"],
            "address": df["住所"],
            "lat": pd.to_numeric(df["緯度"], errors="coerce"),
            "lon": pd.to_numeric(df["経度"], errors="coerce"),
        }
    ).dropna(subset=["lat", "lon"])
    out = out[(out.lat.between(34, 37.5)) & (out.lon.between(138, 141.5))]
    out.to_csv(OUT / out_name, index=False, compression="gzip")
    print(f"{out_name}: {len(out)}件（座標なし・範囲外を除く）")


def build_future_pop() -> None:
    rows = []
    bands65 = ["65～69歳", "70～74歳", "75～79歳", "80～84歳", "85～89歳", "90～94歳", "95歳～"]
    for code in PREFS:
        x = pd.ExcelFile(RAW_IPSS / f"{code}.xlsx")
        for sheet in x.sheet_names[1:]:  # 先頭は県計
            d = pd.read_excel(x, sheet, header=None)
            mcode, name = str(d.iloc[1, 0]).zfill(5), str(d.iloc[1, 1])
            if mcode in CITY_TOTAL_CODES:
                continue
            t = d.iloc[4:25, :8].set_index(0)
            t.columns = YEARS
            t.index = t.index.astype(str).str.strip()
            t = t.apply(pd.to_numeric, errors="coerce")
            for y in YEARS:
                rows.append(
                    {
                        "code": mcode,
                        "pref_code": code,
                        "name": name,
                        "year": y,
                        "pop_total": t.loc["総数", y],
                        "e65": t.loc[bands65, y].sum(),
                        "e75": t.loc[bands65[2:], y].sum(),
                        "e85": t.loc[bands65[4:], y].sum(),
                    }
                )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "future_pop.csv.gz", index=False, compression="gzip")
    print(f"future_pop.csv.gz: {df.code.nunique()}市区町村 × {len(YEARS)}時点")


def geocode_competitors(sleep: float = 0.25) -> None:
    """座標の無い在支診・在支病を国土地理院で補完（結果はキャッシュして再利用）。"""
    sys_path = str(ROOT)
    import sys

    sys.path.insert(0, sys_path)
    from briefing.wakasa_brief.engine import Engine

    cache_path = OUT / "zaishishin_gsi.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    z = Engine(clinics=[]).competitors
    todo = z[z.lat.isna()]
    print(f"在支診・在支病 座標なし {len(todo)}件 → 国土地理院で補完")
    for _, r in todo.iterrows():
        key = str(r.medical_code) + "|" + str(r.address)
        if key in cache:
            continue
        q = f"{r.pref_name}{str(r.address).split(' ')[0].split('　')[0]}"
        try:
            with urllib.request.urlopen(GSI_URL + urllib.parse.quote(q), timeout=20) as resp:
                hits = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print("  失敗:", q, e)
            continue
        if hits:
            lon, lat = hits[0]["geometry"]["coordinates"]
            cache[key] = {"lat": lat, "lon": lon, "title": hits[0]["properties"].get("title", "")}
        else:
            cache[key] = None
        time.sleep(sleep)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    ok = sum(1 for v in cache.values() if v)
    print(f"zaishishin_gsi.json: {ok}/{len(cache)}件 補完")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--skip-geocode", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.no_fetch:
        for c in ("430", "130"):
            fetch(FAC_URL.format(code=c), RAW_FAC / f"jigyosho_{c}.csv")
        for p in PREFS:
            fetch(IPSS_URL.format(code=p), RAW_IPSS / f"{p}.xlsx")
    build_offices("430", "cm_offices.csv.gz")
    build_offices("130", "nursing_stations.csv.gz")
    build_future_pop()
    if not args.skip_geocode:
        geocode_competitors()


if __name__ == "__main__":
    main()
