#!/usr/bin/env python3
"""浦和圏向けに埼玉の未取得区市の在支診・在支病を追記する。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_accuracy_datasets import gsi_geocode, scrape_jmap_city  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
POINTS = PROCESSED / "facility_points.json"
CACHE = PROCESSED / "geocode_cache.json"
MUNICIPAL = PROCESSED / "municipal_home_support_facilities.json"

# JIS codes (municipal JSON + 川口・戸田・蕨)
EXTRA = [
    ("さいたま市北区", "11102", "埼玉県"),
    ("さいたま市大宮区", "11103", "埼玉県"),
    ("さいたま市見沼区", "11104", "埼玉県"),
    ("さいたま市中央区", "11105", "埼玉県"),
    ("さいたま市桜区", "11106", "埼玉県"),
    ("さいたま市緑区", "11109", "埼玉県"),
    ("さいたま市岩槻区", "11110", "埼玉県"),
    ("川口市", "11203", "埼玉県"),
    ("戸田市", "11224", "埼玉県"),
    ("蕨市", "11223", "埼玉県"),
]


def main() -> None:
    data = json.loads(POINTS.read_text(encoding="utf-8"))
    facilities = data["facilities"]
    have_ids = {str(f["id"]) for f in facilities}
    have_muni = {f["municipality"] for f in facilities}
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    municipal = json.loads(MUNICIPAL.read_text(encoding="utf-8"))

    # seed municipal stubs for cities missing from e-Stat scrape
    for name, code, _pref in EXTRA:
        if name not in municipal:
            municipal[name] = {
                "home_support_clinics": None,
                "home_support_hospitals": None,
                "jis_code": code,
                "source": "JIS stub for facility scrape",
            }

    added = 0
    for name, code, pref in EXTRA:
        if name in have_muni and name.startswith("さいたま"):
            # still allow if empty? skip if already have points
            n = sum(1 for f in facilities if f["municipality"] == name)
            if n > 0:
                print(f"skip {name}: already {n}")
                continue
        for kind in ("clinic", "hospital"):
            try:
                facs = scrape_jmap_city(code, kind)
            except Exception as e:
                print(f"ERR {name} {kind}: {e}")
                facs = []
            print(f"{name} {kind}: {len(facs)}")
            for f in facs:
                if str(f["id"]) in have_ids:
                    continue
                f["municipality"] = name
                f["pref"] = pref
                key = f"{pref}|{f['address']}"
                if key in cache and cache[key]:
                    latlon = cache[key]
                else:
                    latlon = gsi_geocode(pref, f["address"])
                    cache[key] = latlon
                    time.sleep(0.05)
                if latlon:
                    f["lat"], f["lon"] = latlon
                    f["geocode"] = "gsi"
                else:
                    f["lat"] = f["lon"] = None
                    f["geocode"] = "failed"
                facilities.append(f)
                have_ids.add(str(f["id"]))
                added += 1
        time.sleep(0.1)

    data["facilities"] = facilities
    data["facility_count"] = len(facilities)
    data["geocoded_count"] = sum(1 for f in facilities if f.get("lat") is not None)
    data["note"] = "Expanded Saitama wards/cities for 浦和 catchment (2026-07)"
    POINTS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    MUNICIPAL.write_text(json.dumps(municipal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"added={added} total={len(facilities)} geocoded={data['geocoded_count']}")


if __name__ == "__main__":
    main()
