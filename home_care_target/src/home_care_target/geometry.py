"""円近似によるポリゴン交差重みと距離計算。"""

from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _circle_intersection_area(r: float, R: float, d: float) -> float:
    """2円の交差面積。r,R=半径, d=中心間距離。"""
    if d >= r + R:
        return 0.0
    if d <= abs(R - r):
        return math.pi * min(r, R) ** 2
    if d == 0 and r == R:
        return math.pi * r ** 2
    r2, R2 = r * r, R * R
    alpha = math.acos(max(-1.0, min(1.0, (d * d + r2 - R2) / (2 * d * r))))
    beta = math.acos(max(-1.0, min(1.0, (d * d + R2 - r2) / (2 * d * R))))
    return (
        r2 * alpha
        + R2 * beta
        - 0.5
        * (
            (-d + r + R)
            * (d + r - R)
            * (d - r + R)
            * (d + r + R)
        )
        ** 0.5
    )


def circle_intersection_weight(
    distance_km: float,
    radius_km: float,
    area_km2: float,
) -> float:
    """市区町村を等面積円で近似し、分析半径円との交差面積 / 市区町村面積 を重みとする。

    完全包含なら 1.0、一部交差なら交差割合、非交差なら 0。
    """
    if area_km2 <= 0:
        return 0.0
    muni_r = math.sqrt(area_km2 / math.pi)
    # 中心が半径内で市区町村が小さい場合の下限は付けず、幾何のみ
    inter = _circle_intersection_area(radius_km, muni_r, distance_km)
    muni_area = math.pi * muni_r * muni_r
    w = inter / muni_area if muni_area > 0 else 0.0
    return max(0.0, min(1.0, w))


def legacy_centroid_weight(distance_km: float, radius_km: float, area_km2: float) -> float:
    """旧方式（後方互換）。"""
    if distance_km > radius_km:
        return 0.0
    ratio = min(
        1.0,
        (radius_km - distance_km + 3.0) / (math.sqrt(max(area_km2, 0.1)) + 3.0),
    )
    return max(0.15, min(1.0, ratio))
