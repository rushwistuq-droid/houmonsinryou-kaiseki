#!/usr/bin/env python3
"""e-Stat CSV を processed JSON に再変換するスクリプト。"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

PREF_SUFFIX = {
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
    "全国": "全国",
}


def clean_name(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s or "")


def parse_num(x):
    x = (x or "").strip().replace(",", "")
    if x in ("", "-", "－", "―", "…"):
        return None
    return int(x)


def rebuild() -> None:
    rows = list(
        csv.reader(
            open(RAW / "estat_r5_t108_zaitaku_shien_shinryojo.csv", encoding="utf-8")
        )
    )
    prefs, cities = {}, {}
    section = "pref"
    for r in rows[5:]:
        if not r or not r[0].strip():
            continue
        raw_name = r[0].strip()
        if "再掲" in raw_name:
            section = "city"
            continue
        name = clean_name(raw_name)
        rec = {
            "general_clinics": parse_num(r[1]),
            "home_support_clinics": parse_num(r[2]) or 0,
            "linked_facilities": parse_num(r[3]) or 0,
            "patients_managed": parse_num(r[4]) or 0,
            "source": "e-Stat 令和5年医療施設調査 都道府県編 第108表",
            "as_of": "2023-10-01",
        }
        if rec["general_clinics"] is None:
            continue
        if section == "pref":
            prefs[PREF_SUFFIX.get(name, name)] = rec
        else:
            cities[name] = rec

    rows = list(
        csv.reader(
            open(
                RAW / "estat_r5_t24_zaitaku_shien_shinryojo_2ji.csv", encoding="utf-8"
            )
        )
    )
    secondary = {}
    for r in rows[5:]:
        if not r or not r[0].strip():
            continue
        raw = r[0].replace("\u3000", " ").strip()
        m = re.match(r"^(\d{2,4})\s+(.+)$", raw)
        if not m:
            continue
        code, nm = m.group(1), clean_name(m.group(2))
        level = "secondary" if len(code) == 4 else "prefecture"
        rec = {
            "code": code,
            "name": nm,
            "level": level,
            "general_clinics": parse_num(r[1]),
            "home_support_clinics": parse_num(r[2]) or 0,
            "linked_facilities": parse_num(r[3]) or 0,
            "patients_managed": parse_num(r[4]) or 0,
            "source": "e-Stat 令和5年医療施設調査 二次医療圏編 第24表",
            "as_of": "2023-10-01",
        }
        if rec["general_clinics"] is None:
            continue
        secondary[code] = rec

    (OUT / "prefecture_home_support_clinics.json").write_text(
        json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "city_home_support_clinics.json").write_text(
        json.dumps(cities, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "secondary_home_support_clinics.json").write_text(
        json.dumps(secondary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"rebuilt prefs={len(prefs)} cities={len(cities)} secondary={len(secondary)}")


if __name__ == "__main__":
    rebuild()
