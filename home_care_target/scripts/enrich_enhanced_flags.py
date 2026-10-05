#!/usr/bin/env python3
"""既存 facility_points に JMAP の機能強化型区分（1/2/3）を付与する。"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_accuracy_datasets import scrape_jmap_city  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
POINTS = PROCESSED / "facility_points.json"
UA = {"User-Agent": "home-care-target/0.5 (enhanced subtype enrich)"}


def scrape_typed(city_code: str, kind: str, subtype: str) -> list[dict]:
    """kind: clinic|hospital, subtype: 1|2|3"""
    typ = f"type_zaitaku_{kind}:{subtype}"
    ftype = "home_support_clinic" if kind == "clinic" else "home_support_hospital"
    facilities = []
    page = 1
    while page <= 30:
        url = (
            f"https://jmap.jp/facilities/search/{typ}/"
            f"searchArea:city/searchId:{city_code}/page:{page}"
        )
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", "replace")
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
                    "facility_type": ftype,
                    "subtype": subtype,
                    "enhanced": subtype in ("1", "2"),
                    "enhanced_kind": (
                        "solo" if subtype == "1" else "joint" if subtype == "2" else "standard"
                    ),
                }
            )
            found += 1
        if found == 0:
            break
        if found < 20:
            break
        page += 1
        time.sleep(0.12)
    return facilities


def main() -> None:
    data = json.loads(POINTS.read_text(encoding="utf-8"))
    facilities = data["facilities"]
    by_id = {str(f["id"]): f for f in facilities}
    codes = sorted({str(f["jis_code"]) for f in facilities if f.get("jis_code")})
    print(f"enriching {len(codes)} cities, {len(facilities)} facilities")

    marked = 0
    for i, code in enumerate(codes):
        for kind in ("clinic", "hospital"):
            for subtype in ("1", "2", "3"):
                try:
                    rows = scrape_typed(code, kind, subtype)
                except Exception as e:
                    print(f"ERR {code} {kind}:{subtype}: {e}")
                    rows = []
                for r in rows:
                    fid = str(r["id"])
                    if fid not in by_id:
                        continue
                    by_id[fid]["subtype"] = r["subtype"]
                    by_id[fid]["enhanced"] = r["enhanced"]
                    by_id[fid]["enhanced_kind"] = r["enhanced_kind"]
                    marked += 1
                time.sleep(0.05)
        if (i + 1) % 10 == 0:
            print(f"[{i+1}/{len(codes)}] marked_updates={marked}")

    # default unmarked to standard (not enhanced)
    unknown = 0
    for f in facilities:
        if "enhanced" not in f:
            f["enhanced"] = False
            f["enhanced_kind"] = "unknown"
            f["subtype"] = None
            unknown += 1

    enh = sum(1 for f in facilities if f.get("enhanced"))
    data["facilities"] = facilities
    data["enhanced_marked"] = enh
    data["enhanced_unknown"] = unknown
    data["note_enhanced"] = "JMAP type_zaitaku_{clinic|hospital}:{1,2,3} (1/2=機能強化型)"
    POINTS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done enhanced={enh} unknown={unknown} total={len(facilities)}")


if __name__ == "__main__":
    main()
