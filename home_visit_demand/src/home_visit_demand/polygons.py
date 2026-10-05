#!/usr/bin/env python3
"""市区町村ポリゴンと円の面積交差による人口按分（メッシュ補完・検証用）。

JapanCityGeoJson（市区町村単位）を用い、円との交差面積比で人口を按分する。
shapely が無い環境では bbox 近似にフォールバックする。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

BOUNDARY_DIR = Path("/tmp/accuracy/boundary/cities")  # geojson/NN/*.json への展開先でも可


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def circle_polygon_intersection_ratio(geom, lat: float, lon: float, radius_km: float) -> float:
    """ポリゴン面積に対する円交差面積比。"""
    try:
        from shapely.geometry import Point, mapping, shape
        from shapely.ops import transform
        import pyproj
    except ImportError:
        # bbox 近似
        return _bbox_ratio(geom, lat, lon, radius_km)

    poly = shape(geom)
    # 局所投影
    proj = pyproj.Proj(proj="aeqd", lat_0=lat, lon_0=lon, units="m")
    wgs84 = pyproj.Proj("EPSG:4326")
    project = pyproj.Transformer.from_proj(wgs84, proj, always_xy=True).transform
    poly_m = transform(project, poly)
    circle = Point(0, 0).buffer(radius_km * 1000.0)
    if poly_m.area <= 0:
        return 0.0
    inter = poly_m.intersection(circle)
    return float(inter.area / poly_m.area)


def _bbox_ratio(geom, lat, lon, radius_km) -> float:
    """座標列のbbox中心距離による粗い近似。"""
    coords = []
    def walk(g):
        if isinstance(g[0], (float, int)):
            coords.append((g[1], g[0]))  # lat, lon if geojson lon,lat
            return
        for x in g:
            walk(x)
    walk(geom["coordinates"] if isinstance(geom, dict) else geom)
    if not coords:
        # geojson is lon,lat
        def walk2(obj):
            if isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], (int, float)):
                coords.append((obj[1], obj[0]))
            elif isinstance(obj, (list, tuple)):
                for x in obj:
                    walk2(x)
        walk2(geom.get("coordinates") if isinstance(geom, dict) else geom)
    if not coords:
        return 0.0
    clat = sum(c[0] for c in coords) / len(coords)
    clon = sum(c[1] for c in coords) / len(coords)
    d = haversine_km(lat, lon, clat, clon)
    if d <= radius_km:
        return max(0.2, 1.0 - d / (radius_km * 1.5))
    return 0.0


def load_city_geojson(code5: str) -> dict | None:
    pref = code5[:2]
    # 個別ファイル
    p = Path(f"/tmp/accuracy/boundary/geojson/{pref}/{code5}.json")
    if not p.exists():
        p = Path(f"/tmp/accuracy/boundary/cities_indiv/{pref}/{code5}.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None
