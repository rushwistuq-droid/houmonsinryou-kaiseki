#!/usr/bin/env python3
"""在支診・在支病名簿（関東信越厚生局）を最新版に更新する（要ネット接続）。

    python3 briefing/scripts/update_zaishishin.py --tag r0809 --as-of 2026-08-01

厚生局の「届出受理医療機関名簿（医科）」zip を取得し、系統B（home_visit_demand/scripts/build_zaishishin.py）
と同じ規則で在支診・在支病を抽出する。座標は旧版から医療機関番号で引き継ぎ、新規分は
engine 側の JMAP突合 → 国土地理院（build_extra_datasets.py の geocode）で補う。

出力: briefing/data/processed/zaishishin_latest.csv.gz と zaishishin_latest_meta.json
（engine.py はこれがあれば系統Bの旧版より優先して使う）
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "home_visit_demand/data/zaishishin_raw"
OLD = ROOT / "home_visit_demand/data/processed/zaishishin.csv.gz"
OUT = ROOT / "briefing/data/processed"
URL = "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/shisetsu_ika_{tag}.zip"
TARGET_PREFS = ("11", "12", "13", "14")
KINDS = (("在宅療養支援診療所", re.compile("在宅療養支援診療所")), ("在宅療養支援病院", re.compile("在宅療養支援病院")))


def fetch(tag: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"shisetsu_ika_{tag}.zip"
    if not dest.exists():
        print("GET", URL.format(tag=tag))
        urllib.request.urlretrieve(URL.format(tag=tag), dest)
    out_dir = RAW / f"shisetsu_ika_{tag}"
    with zipfile.ZipFile(dest) as zf:
        zf.extractall(out_dir)
    return out_dir


def load(base: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(base.rglob("*.xlsx")):
        code = path.name[:2]
        if code not in TARGET_PREFS:
            continue
        print("reading", path.name)
        df = pd.read_excel(path, header=3)
        for kind, rx in KINDS:
            sub = df[df["受理届出名称"].astype(str).str.contains(rx)].copy()
            if len(sub):
                sub["pref_code"], sub["kind"] = code, kind
                rows.append(sub)
    all_df = pd.concat(rows, ignore_index=True)
    agg = lambda s: "|".join(sorted({str(x) for x in s if str(x) not in ("", "nan")}))  # noqa: E731
    out = all_df.groupby(["pref_code", "医療機関番号", "kind"], as_index=False).agg(
        pref_name=("都道府県名", "first"),
        name=("医療機関名称", "first"),
        address=("医療機関所在地（住所）", "first"),
        zaishi_class=("受理記号", agg),
        acceptance_name=("受理届出名称", "first"),
    )
    out = out.rename(columns={"医療機関番号": "medical_code"})
    out["pref_code"] = out.pref_code.astype(int)
    return out


def carry_coords(new: pd.DataFrame) -> pd.DataFrame:
    old = pd.read_csv(OLD)
    keep = old.dropna(subset=["lat"]).drop_duplicates(["medical_code", "kind"])[["medical_code", "kind", "lat", "lon", "match_how"]]
    new["medical_code"] = pd.to_numeric(new.medical_code, errors="coerce")
    return new.merge(keep, on=["medical_code", "kind"], how="left")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="r0809", help="厚生局ファイル名の版（例 r0809）")
    ap.add_argument("--as-of", default="2026-08-01")
    args = ap.parse_args()
    base = fetch(args.tag)
    new = carry_coords(load(base))
    new["source"] = f"関東信越厚生局 届出受理医療機関名簿（医科）{args.as_of}現在"
    OUT.mkdir(parents=True, exist_ok=True)
    new.to_csv(OUT / "zaishishin_latest.csv.gz", index=False, compression="gzip")
    old = pd.read_csv(OLD)
    old_ids = set(zip(old.medical_code, old.kind))
    new_ids = set(zip(new.medical_code, new.kind))
    meta = {
        "as_of": args.as_of,
        "total": int(len(new)),
        "clinics": int((new.kind == "在宅療養支援診療所").sum()),
        "hospitals": int((new.kind == "在宅療養支援病院").sum()),
        "added_since_previous": int(len(new_ids - old_ids)),
        "removed_since_previous": int(len(old_ids - new_ids)),
        "coords_carried_over": int(new.lat.notna().sum()),
    }
    (OUT / "zaishishin_latest_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
