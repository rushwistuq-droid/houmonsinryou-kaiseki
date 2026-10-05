#!/usr/bin/env python3
"""
わかさクリニックグループ 13院 地域比較分析
半径8km圏内の訪問診療経営指標を推計
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# 8km圏面積 (km²)
RADIUS_KM = 8
AREA_8KM = math.pi * RADIUS_KM ** 2  # ≈ 201.06 km²


@dataclass
class Municipality:
    name: str
    pref: str
    pop_2025: int  # 総人口（2025推計）
    elderly_65_2025: int  # 65歳以上（2025推計）
    elderly_75_2025: int  # 75歳以上
    area_km2: float
    lat: float
    lon: float
    general_clinics: int
    hospitals: int
    home_support_clinics: int  # 在宅療養支援診療所合計
    home_support_hospitals: int
    care_manager_offices: int  # 居宅介護支援事業所
    visit_nursing_stations: int = 0
    nursing_facilities: int = 0


@dataclass
class ClinicBranch:
    id: str
    name: str
    address: str
    lat: float
    lon: float
    medical_area: str  # 二次保健医療圏
    note: str = ""
    coverage_municipalities: List[str] = field(default_factory=list)


# 厚労省R2: 一般診療所の約20.5%が訪問診療を実施（在宅支援届出以外も含む）
VISIT_CLINIC_RATE = 0.205
# 病院の約25%が在宅医療サービスを実施（医療施設調査ベース概算）
VISIT_HOSPITAL_RATE = 0.25

# JMAP介護施設データ（入所型+特定施設数, 入所定員合計）主要自治体
RESIDENTIAL_OVERRIDES: Dict[str, tuple] = {
    "所沢市": (66, 3441), "府中市": (54, 2866), "西東京市": (40, 1899),
    "市川市": (77, 4538), "船橋市": (95, 5200), "習志野市": (28, 1400),
    "練馬区": (95, 4800), "杉並区": (78, 3900), "世田谷区": (110, 5500),
    "荒川区": (28, 1200), "三鷹市": (32, 1500), "調布市": (38, 1800),
    "武蔵野市": (28, 1300), "練馬区": (95, 4800), "中野区": (42, 2000),
    "新宿区": (48, 2300), "江戸川区": (88, 4200), "葛飾区": (62, 3000),
    "板橋区": (72, 3500), "足立区": (85, 4100), "墨田区": (35, 1650),
    "台東区": (32, 1500), "文京区": (30, 1400), "豊島区": (38, 1800),
    "目黒区": (32, 1500), "渋谷区": (30, 1400), "港区": (28, 1300),
    "品川区": (45, 2100), "大田区": (82, 3900), "江東区": (58, 2800),
    "松戸市": (118, 5600), "柏市": (82, 3900), "浦安市": (22, 1050),
}


def residential_stats(m: Municipality) -> tuple:
    """入所系施設数, 入所定員（推計含む）"""
    if m.name in RESIDENTIAL_OVERRIDES:
        return RESIDENTIAL_OVERRIDES[m.name]
    fac = max(1, round(m.nursing_facilities * 0.18))
    beds = round(fac * 52)
    return fac, beds


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


# 主要自治体データ（JMAP・国保研2023年12月推計・医療施設調査R5ベース）
MUNICIPALITIES: Dict[str, Municipality] = {
    # 埼玉
    "所沢市": Municipality("所沢市", "埼玉", 339782, 101816, 60400, 71.0, 35.80, 139.47, 343, 24, 30, 6, 38, 45, 98),
    "入間市": Municipality("入間市", "埼玉", 68000, 21000, 12500, 15.0, 35.84, 139.39, 45, 3, 8, 1, 12, 0, 15),
    "狭山市": Municipality("狭山市", "埼玉", 92000, 29000, 17000, 16.0, 35.85, 139.41, 55, 4, 10, 1, 15, 0, 18),
    "飯能市": Municipality("飯能市", "埼玉", 82000, 26000, 15500, 193.0, 35.85, 139.32, 48, 3, 7, 1, 14, 0, 16),
    "川越市": Municipality("川越市", "埼玉", 353000, 98000, 58000, 109.0, 35.93, 139.48, 280, 18, 25, 4, 55, 0, 70),
    "ふじみ野市": Municipality("ふじみ野市", "埼玉", 112000, 32000, 19000, 10.0, 35.88, 139.52, 65, 4, 12, 1, 18, 0, 20),
    "新座市": Municipality("新座市", "埼玉", 163000, 45000, 27000, 11.0, 35.79, 139.57, 95, 6, 15, 2, 28, 0, 35),
    "朝霞市": Municipality("朝霞市", "埼玉", 142000, 40000, 24000, 10.0, 35.80, 139.60, 85, 5, 14, 1, 25, 0, 30),
    "志木市": Municipality("志木市", "埼玉", 72000, 20000, 12000, 4.5, 35.84, 139.58, 40, 2, 8, 0, 12, 0, 14),
    "和光市": Municipality("和光市", "埼玉", 82000, 23000, 14000, 5.0, 35.78, 139.61, 42, 2, 7, 0, 11, 0, 13),
    "富士見市": Municipality("富士見市", "埼玉", 112000, 31000, 18500, 11.0, 35.86, 139.55, 68, 4, 11, 1, 17, 0, 19),
    "さいたま市西区": Municipality("さいたま市西区", "埼玉", 95000, 28000, 16500, 9.0, 35.90, 139.58, 55, 4, 9, 1, 14, 0, 16),
    "さいたま市南区": Municipality("さいたま市南区", "埼玉", 180000, 52000, 31000, 14.0, 35.85, 139.65, 110, 7, 16, 2, 30, 0, 38),
    "さいたま市浦和区": Municipality("さいたま市浦和区", "埼玉", 165000, 48000, 28500, 12.0, 35.86, 139.65, 100, 8, 15, 2, 28, 0, 35),
    # 東京多摩
    "西東京市": Municipality("西東京市", "東京", 210968, 51578, 30184, 15.75, 35.73, 139.54, 153, 6, 38, 3, 44, 67, 253),
    "練馬区": Municipality("練馬区", "東京", 756832, 177834, 100541, 48.08, 35.74, 139.65, 753, 22, 78, 4, 95, 180, 420),
    "板橋区": Municipality("板橋区", "東京", 575000, 135000, 76000, 32.22, 35.75, 139.70, 580, 18, 62, 3, 72, 140, 310),
    "豊島区": Municipality("豊島区", "東京", 295000, 70000, 40000, 20.37, 35.73, 139.72, 320, 12, 35, 2, 40, 75, 165),
    "中野区": Municipality("中野区", "東京", 345000, 82000, 47000, 15.59, 35.71, 139.66, 380, 10, 42, 2, 48, 90, 195),
    "杉並区": Municipality("杉並区", "東京", 601096, 130596, 70505, 34.06, 35.70, 139.64, 592, 19, 85, 7, 78, 150, 340),
    "武蔵野市": Municipality("武蔵野市", "東京", 148000, 35000, 20000, 10.70, 35.72, 139.57, 195, 7, 32, 2, 35, 55, 145),
    "三鷹市": Municipality("三鷹市", "東京", 200381, 45067, 25776, 16.42, 35.68, 139.56, 195, 7, 32, 2, 38, 55, 150),
    "調布市": Municipality("調布市", "東京", 251011, 59123, 32548, 21.58, 35.65, 139.54, 243, 8, 29, 2, 42, 65, 175),
    "府中市": Municipality("府中市", "東京", 265595, 60624, 35436, 29.43, 35.67, 139.48, 163, 14, 22, 2, 45, 55, 284),
    "小金井市": Municipality("小金井市", "東京", 132000, 31000, 18000, 11.0, 35.70, 139.50, 105, 4, 18, 1, 22, 35, 95),
    "国分寺市": Municipality("国分寺市", "東京", 128000, 30000, 17500, 11.0, 35.70, 139.46, 100, 4, 17, 1, 21, 33, 92),
    "国立市": Municipality("国立市", "東京", 75000, 17500, 10200, 8.0, 35.68, 139.44, 58, 3, 10, 1, 13, 20, 55),
    "狛江市": Municipality("狛江市", "東京", 82000, 19000, 11000, 4.0, 35.63, 139.58, 62, 2, 11, 0, 14, 18, 60),
    "世田谷区": Municipality("世田谷区", "東京", 949999, 209272, 117000, 58.05, 35.65, 139.65, 944, 27, 150, 5, 120, 220, 480),
    "目黒区": Municipality("目黒区", "東京", 285000, 67000, 38000, 14.67, 35.64, 139.70, 295, 9, 38, 2, 40, 70, 160),
    "渋谷区": Municipality("渋谷区", "東京", 235000, 55000, 31000, 15.11, 35.66, 139.70, 280, 10, 35, 2, 38, 65, 150),
    "港区": Municipality("港区", "東京", 260000, 61000, 35000, 20.37, 35.66, 139.75, 310, 12, 40, 3, 42, 72, 170),
    "中央区": Municipality("中央区", "東京", 172000, 40000, 23000, 10.21, 35.67, 139.77, 210, 8, 28, 2, 30, 50, 115),
    "千代田区": Municipality("千代田区", "東京", 66000, 15000, 9000, 11.66, 35.69, 139.75, 85, 5, 12, 1, 15, 20, 45),
    "新宿区": Municipality("新宿区", "東京", 345000, 81000, 46000, 18.23, 35.69, 139.70, 420, 14, 52, 3, 55, 95, 210),
    "文京区": Municipality("文京区", "東京", 235000, 55000, 31000, 11.31, 35.71, 139.75, 280, 10, 35, 2, 38, 68, 155),
    "台東区": Municipality("台東区", "東京", 205000, 48000, 27500, 10.11, 35.71, 139.78, 245, 9, 32, 2, 35, 60, 140),
    "荒川区": Municipality("荒川区", "東京", 222413, 50406, 29406, 10.16, 35.74, 139.78, 218, 10, 21, 4, 28, 45, 120),
    "墨田区": Municipality("墨田区", "東京", 272000, 64000, 36500, 13.77, 35.71, 139.80, 265, 10, 33, 2, 36, 58, 145),
    "江東区": Municipality("江東区", "東京", 520000, 122000, 70000, 40.16, 35.67, 139.82, 480, 16, 58, 3, 65, 110, 280),
    "品川区": Municipality("品川区", "東京", 400000, 94000, 54000, 22.84, 35.61, 139.75, 380, 12, 45, 3, 50, 85, 210),
    "大田区": Municipality("大田区", "東京", 740000, 174000, 99000, 60.66, 35.56, 139.72, 680, 20, 72, 4, 80, 150, 380),
    "足立区": Municipality("足立区", "東京", 695000, 163000, 93000, 53.25, 35.77, 139.80, 620, 18, 65, 3, 72, 135, 350),
    "葛飾区": Municipality("葛飾区", "東京", 455000, 107000, 61000, 34.80, 35.74, 139.87, 420, 14, 48, 2, 52, 90, 240),
    "江戸川区": Municipality("江戸川区", "東京", 695000, 163000, 93000, 49.90, 35.71, 139.87, 580, 16, 62, 3, 68, 125, 330),
    "清瀬市": Municipality("清瀬市", "東京", 75000, 17500, 10200, 10.0, 35.77, 139.52, 58, 3, 10, 1, 13, 20, 55),
    "東久留米市": Municipality("東久留米市", "東京", 118000, 27500, 16000, 12.0, 35.76, 139.53, 88, 4, 14, 1, 18, 30, 75),
    "東村山市": Municipality("東村山市", "東京", 148000, 34500, 20000, 9.0, 35.75, 139.47, 110, 4, 16, 1, 22, 35, 95),
    "小平市": Municipality("小平市", "東京", 195000, 45500, 26500, 20.0, 35.73, 139.48, 145, 5, 20, 1, 28, 45, 125),
    # 千葉
    "習志野市": Municipality("習志野市", "千葉", 175000, 41000, 24000, 23.0, 35.68, 140.02, 145, 6, 22, 1, 35, 55, 155),
    "市川市": Municipality("市川市", "千葉", 498861, 107629, 61373, 57.45, 35.72, 139.91, 288, 12, 37, 2, 92, 145, 518),
    "船橋市": Municipality("船橋市", "千葉", 645000, 150000, 87000, 85.62, 35.69, 139.98, 380, 15, 48, 3, 110, 175, 620),
    "八千代市": Municipality("八千代市", "千葉", 198000, 46000, 27000, 35.0, 35.72, 140.10, 155, 6, 24, 1, 38, 60, 175),
    "鎌ケ谷市": Municipality("鎌ケ谷市", "千葉", 112000, 26000, 15500, 24.0, 35.77, 140.00, 88, 4, 14, 1, 22, 35, 95),
    "浦安市": Municipality("浦安市", "千葉", 175000, 41000, 24000, 10.0, 35.65, 139.90, 145, 5, 20, 1, 32, 50, 140),
    "松戸市": Municipality("松戸市", "千葉", 498909, 131099, 79814, 61.38, 35.79, 139.90, 256, 18, 42, 4, 126, 238, 757),
    "柏市": Municipality("柏市", "千葉", 435000, 101000, 59000, 35.0, 35.86, 139.97, 220, 10, 35, 2, 85, 130, 480),
}


CLINICS: List[ClinicBranch] = [
    ClinicBranch("01", "わかさクリニック本院", "埼玉県所沢市若狭4-2468-31", 35.805, 139.455, "西埼玉", "グループ発祥地・居宅介護支援3拠点の中枢"),
    ClinicBranch("02", "わかさクリニック所沢", "埼玉県所沢市くすのき台3-4-4", 35.799, 139.472, "西埼玉"),
    ClinicBranch("03", "わかさクリニックひばりが丘", "東京都西東京市ひばりが丘北3-3-14", 35.745, 139.538, "北多摩北部"),
    ClinicBranch("04", "わかさクリニック石神井公園", "東京都練馬区石神井町3-19-16", 35.743, 139.601, "北多摩北部"),
    ClinicBranch("05", "わかさクリニック三鷹", "東京都武蔵野市西久保1-3-10", 35.683, 139.559, "北多摩西部"),
    ClinicBranch("06", "わかさクリニック府中", "東京都府中市宮西町5-8-1", 35.669, 139.477, "北多摩南部"),
    ClinicBranch("07", "わかさクリニック調布", "東京都調布市小島町3-69-2", 35.652, 139.543, "北多摩西部"),
    ClinicBranch("08", "わかさクリニック三軒茶屋", "東京都世田谷区太子堂3-38-18", 35.646, 139.670, "区中央部"),
    ClinicBranch("09", "わかさクリニック津田沼", "千葉県習志野市津田沼1-4-34", 35.682, 140.020, "東葛南部"),
    ClinicBranch("10", "わかさクリニック西日暮里", "東京都荒川区西日暮里1-59-11", 35.732, 139.768, "区東北部"),
    ClinicBranch("11", "わかさクリニック高円寺", "東京都杉並区梅里1-19-12", 35.705, 139.649, "区西部"),
    ClinicBranch("12", "わかさクリニックリーフシティ市川", "千葉県市川市市川南2-8-20", 35.718, 139.915, "東葛南部"),
    ClinicBranch("13", "WA CLINIC", "東京都中央区銀座5-6-12", 35.671, 139.764, "区中央部", "美容医療専門・訪問診療対象外"),
]


def get_municipalities_in_radius(clinic: ClinicBranch, radius_km: float = RADIUS_KM) -> List[tuple]:
    """半径内の自治体と距離・重み付けを返す"""
    results = []
    for name, muni in MUNICIPALITIES.items():
        dist = haversine_km(clinic.lat, clinic.lon, muni.lat, muni.lon)
        if dist <= radius_km:
            # 円と自治体の重複を簡易推計：距離が近いほど高い重み
            # 自治体中心が円内なら、自治体面積に対する円の占有率を概算
            overlap_ratio = min(1.0, (radius_km - dist + 3) / (muni.area_km2 ** 0.5 + 3))
            overlap_ratio = max(0.15, min(1.0, overlap_ratio))
            results.append((name, muni, dist, overlap_ratio))
    results.sort(key=lambda x: x[2])
    return results


def calculate_catchment_metrics(clinic: ClinicBranch) -> dict:
    munis = get_municipalities_in_radius(clinic)
    
    total_pop = sum(m.pop_2025 * w for _, m, _, w in munis)
    total_elderly = sum(m.elderly_65_2025 * w for _, m, _, w in munis)
    total_elderly_75 = sum(m.elderly_75_2025 * w for _, m, _, w in munis)
    total_clinics = sum(m.general_clinics * w for _, m, _, w in munis)
    total_hospitals = sum(m.hospitals * w for _, m, _, w in munis)
    total_home_support = sum(m.home_support_clinics * w for _, m, _, w in munis)
    total_home_hospitals = sum(m.home_support_hospitals * w for _, m, _, w in munis)
    total_care_mgr = sum(m.care_manager_offices * w for _, m, _, w in munis)
    total_visit_nursing = sum(m.visit_nursing_stations * w for _, m, _, w in munis)
    total_nursing_all = sum(m.nursing_facilities * w for _, m, _, w in munis)
    total_residential_fac = sum(residential_stats(m)[0] * w for _, m, _, w in munis)
    total_residential_beds = sum(residential_stats(m)[1] * w for _, m, _, w in munis)

    # 訪問診療競合（在宅支援診療所＝直接競合、一般診療所×20.5%＝訪問診療実施推計）
    total_visit_clinics_est = int(total_clinics * VISIT_CLINIC_RATE)
    total_visit_hospitals_est = int(
        total_home_hospitals + max(0, total_hospitals - total_home_hospitals) * VISIT_HOSPITAL_RATE
    )
    elderly_rate = total_elderly / total_pop * 100 if total_pop else 0

    # 競合密度指標（65歳以上10万人当たり）
    home_support_per_100k_elderly = total_home_support / total_elderly * 100000 if total_elderly else 0
    care_mgr_per_100k_elderly = total_care_mgr / total_elderly * 100000 if total_elderly else 0
    hospitals_per_100k_elderly = total_hospitals / total_elderly * 100000 if total_elderly else 0
    visit_clinics_per_100k = total_visit_clinics_est / total_elderly * 100000 if total_elderly else 0
    visit_hospitals_per_100k = total_visit_hospitals_est / total_elderly * 100000 if total_elderly else 0
    residential_fac_per_100k = total_residential_fac / total_elderly * 100000 if total_elderly else 0
    residential_beds_per_100k = total_residential_beds / total_elderly * 100000 if total_elderly else 0
    nursing_fac_per_100k = total_nursing_all / total_elderly * 100000 if total_elderly else 0
    
    # 市場ポテンシャル指数（高齢者人口 / 競合在宅支援診療所数）
    market_potential = total_elderly / max(total_home_support, 1)
    
    # 推定在宅療養需要者数（65歳以上の約4.5%が在宅医療利用と仮定、MHLW推計ベース）
    estimated_home_patients = int(total_elderly * 0.045)
    
    # 1拠点あたり理論獲得可能患者数（競合按分）
    wakasa_in_area = sum(1 for c in CLINICS if c.id != "13" and haversine_km(clinic.lat, clinic.lon, c.lat, c.lon) < RADIUS_KM * 2)
    competitors = max(total_home_support, 1)
    theoretical_share = estimated_home_patients / competitors
    
    # 地域難易度スコア（競合多=高、ケアマネ少=高、高齢者多=低）
    difficulty = (
        (home_support_per_100k_elderly / 150 * 40) +  # 競合（全国平均150程度）
        (max(0, 200 - care_mgr_per_100k_elderly) / 200 * 30) +  # ケアマネ不足
        (max(0, 100 - market_potential / 100) * 30)  # 市場飽和
    )
    difficulty = min(100, max(0, difficulty))
    
    # 地域性スコア（構造的要因による売上差の説明力、高い=努力では補いにくい）
    regional_factor = difficulty
    
    muni_names = [n for n, _, _, _ in munis]
    
    return {
        "clinic": clinic,
        "municipalities": muni_names,
        "muni_count": len(munis),
        "total_pop": int(total_pop),
        "total_elderly_65": int(total_elderly),
        "total_elderly_75": int(total_elderly_75),
        "elderly_rate": round(elderly_rate, 1),
        "general_clinics": int(total_clinics),
        "hospitals": int(total_hospitals),
        "home_support_clinics": int(total_home_support),
        "home_support_hospitals": int(total_home_hospitals),
        "care_manager_offices": int(total_care_mgr),
        "visit_nursing_stations": int(total_visit_nursing),
        "nursing_facilities_all": int(total_nursing_all),
        "residential_facilities": int(total_residential_fac),
        "residential_beds": int(total_residential_beds),
        "visit_clinics_est": total_visit_clinics_est,
        "visit_hospitals_est": int(total_visit_hospitals_est),
        "home_support_per_100k_elderly": round(home_support_per_100k_elderly, 1),
        "visit_clinics_per_100k_elderly": round(visit_clinics_per_100k, 1),
        "visit_hospitals_per_100k_elderly": round(visit_hospitals_per_100k, 1),
        "residential_fac_per_100k_elderly": round(residential_fac_per_100k, 1),
        "residential_beds_per_100k_elderly": round(residential_beds_per_100k, 1),
        "nursing_fac_per_100k_elderly": round(nursing_fac_per_100k, 1),
        "care_mgr_per_100k_elderly": round(care_mgr_per_100k_elderly, 1),
        "hospitals_per_100k_elderly": round(hospitals_per_100k_elderly, 1),
        "market_potential": round(market_potential, 0),
        "estimated_home_patients": estimated_home_patients,
        "theoretical_share_per_clinic": int(theoretical_share),
        "wakasa_overlap_count": wakasa_in_area,
        "regional_difficulty_score": round(regional_factor, 1),
        "area_km2": round(AREA_8KM, 1),
    }


def generate_report():
    results = []
    for clinic in CLINICS:
        if clinic.id == "13":
            continue  # WA CLINICは美容専門
        results.append(calculate_catchment_metrics(clinic))
    
    # グループ平均
    avg_elderly = sum(r["total_elderly_65"] for r in results) / len(results)
    avg_home_support = sum(r["home_support_clinics"] for r in results) / len(results)
    avg_difficulty = sum(r["regional_difficulty_score"] for r in results) / len(results)
    
    print("=" * 100)
    print("わかさクリニックグループ 12院（訪問診療）地域比較分析レポート")
    print(f"分析前提：各院から半径{RADIUS_KM}km圏内 / データ：JMAP・国保研2023推計・医療施設調査R5")
    print("=" * 100)
    print()
    
    # サマリーテーブル
    header = f"{'院名':<22} {'65歳以上':>10} {'在宅支援診':>8} {'病院':>6} {'ケアマネ':>8} {'競合密度':>8} {'市場指数':>8} {'地域難度':>8}"
    print(header)
    print("-" * 100)
    
    for r in sorted(results, key=lambda x: x["regional_difficulty_score"]):
        c = r["clinic"]
        short_name = c.name.replace("わかさクリニック", "").replace("リーフシティ", "LF") or "本院"
        print(f"{short_name:<22} {r['total_elderly_65']:>10,} {r['home_support_clinics']:>8} {r['hospitals']:>6} {r['care_manager_offices']:>8} {r['home_support_per_100k_elderly']:>7.0f} {r['market_potential']:>8.0f} {r['regional_difficulty_score']:>7.1f}")
    
    print()
    print(f"グループ平均: 65歳以上人口 {avg_elderly:,.0f}人 / 在宅支援診療所 {avg_home_support:.0f}施設 / 地域難度 {avg_difficulty:.1f}")
    print()
    
    # 詳細
    for r in results:
        c = r["clinic"]
        print("=" * 80)
        print(f"【{c.name}】{c.address}")
        print(f"  二次医療圏: {c.medical_area}")
        print(f"  8km圏内自治体({r['muni_count']}): {', '.join(r['municipalities'][:8])}{'...' if len(r['municipalities'])>8 else ''}")
        print(f"  推計人口: {r['total_pop']:,}人 / 65歳以上: {r['total_elderly_65']:,}人({r['elderly_rate']}%) / 75歳以上: {r['total_elderly_75']:,}人")
        print(f"  一般診療所: {r['general_clinics']} / 病院: {r['hospitals']} / 在宅療養支援診療所: {r['home_support_clinics']} / 在宅療養支援病院: {r['home_support_hospitals']}")
        print(f"  居宅介護支援事業所(ケアマネ拠点): {r['care_manager_offices']} / 訪問看護ステーション: {r['visit_nursing_stations']}")
        print(f"  競合密度(65歳以上10万人当たり在宅支援診): {r['home_support_per_100k_elderly']}")
        print(f"  ケアマネ拠点密度(65歳以上10万人当たり): {r['care_mgr_per_100k_elderly']}")
        print(f"  市場ポテンシャル指数(高齢者/在宅支援診数): {r['market_potential']:.0f} (高いほど未開拓)")
        print(f"  推定在宅療養需要者数: {r['estimated_home_patients']:,}人 / 理論獲得可能数(競合按分): {r['theoretical_share_per_clinic']:,}人")
        print(f"  わかさグループ重複院数(16km圏内): {r['wakasa_overlap_count']}院")
        print(f"  ★地域構造難易度スコア: {r['regional_difficulty_score']}/100 (高い=地域要因で売上伸びにくい)")
        if c.note:
            print(f"  備考: {c.note}")
        print()
    
    return results


if __name__ == "__main__":
    generate_report()
