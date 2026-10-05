"""地点ごとの指数計算エンジン（院の診断と出店候補地のスコアリングで共用）。

系統B（home_visit_demand）の居宅市場の算式をそのまま使い、
任意の地点を高速に一括計算できるようにしたもの。追加した主な指標:

- 潜在居宅需要: 東京都並みの受療率だった場合の居宅需要（埼玉・千葉の伸びしろの目安）
- 実効競合ユニット: 在支診・在支病を類型別に重み付けした競合量（座標未取得分は県別に補正）
- グループ内重複: 自院が最寄りとなる高齢者の割合（排他率）
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
HVD = ROOT / "home_visit_demand"
HCT = ROOT / "home_care_target"
PROCESSED = ROOT / "briefing/data/processed"
sys.path.insert(0, str(HVD / "src"))

from home_visit_demand.precision import MESH_HALF_DIAG_KM  # noqa: E402

BANDS = ("65-74", "75-84", "85-94", "95+")

RADIUS_KM = 8.0
SIBLING_RADIUS_KM = 16.0
# 1都3県＋隣接県（圏域が県境をまたぐ院のため）
MESH_PREFS = (8, 9, 10, 11, 12, 13, 14, 19)
LATENT_BENCHMARK_PREF = "13"  # 潜在需要の基準＝東京都の受療率
PREF_NAMES = {"11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県"}

# 競合の重み（系統Cの実効競合と同じ考え方）
W_ENHANCED_CLINIC = 1.0  # 機能強化型在支診（支援診1・2）
W_STANDARD_CLINIC = 0.35  # 従来型在支診（支援診3）
W_STANDARD_HOSPITAL_FACTOR = 0.35  # 従来型在支病は病院ウェイト×0.35
OWN_GROUP_PATTERN = re.compile(r"わかさクリニック|元気会")

_KANJI_DIGITS = str.maketrans("一二三四五六七八九", "123456789")


def haversine_km(lat1, lon1, lat2, lon2):
    """ベクトル対応の大円距離（km）。"""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def _project(lat, lon):
    """KD木用の平面近似座標（km）。候補抽出にのみ使い、距離は haversine で再計算する。"""
    return np.column_stack([(np.asarray(lon) - 139.7) * 90.4, (np.asarray(lat) - 35.7) * 110.95])


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    return re.sub(
        r"(社会医療法人財団|社会医療法人社団|社会医療法人|医療法人社団|医療法人財団|特定医療法人|医療法人"
        r"|一般社団法人|一般財団法人|公益財団法人|公益社団法人|社会福祉法人|[\s　・])",
        "",
        s,
    )


def _norm_addr(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"^(東京都|埼玉県|千葉県|神奈川県)", "", s)
    s = re.sub(r"([一二三四五六七八九])丁目", lambda m: m.group(1).translate(_KANJI_DIGITS) + "-", s)
    s = re.sub(r"(丁目|番地|番|号|の)", "-", s)
    s = s.replace("ー", "-").replace("−", "-").replace("‐", "-")
    s = re.sub(r"\s.*$", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s.replace("大字", "").replace("字", "")


@dataclass
class Clinic:
    id: str
    name: str
    lat: float
    lon: float
    pref: str
    home_start: str
    era: str
    note: str = ""
    start_approx: bool = False


def load_clinics(path: Path | None = None) -> list[Clinic]:
    path = path or ROOT / "briefing" / "data" / "clinics.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Clinic(**c) for c in data["clinics"]]


class Engine:
    """データを一度だけ読み込み、地点ごとの指標を返す。"""

    def __init__(self, clinics: list[Clinic] | None = None):
        self.clinics = clinics if clinics is not None else load_clinics()

    # ------------------------------------------------------------------ data
    @cached_property
    def mesh(self) -> pd.DataFrame:
        df = pd.read_csv(HVD / "data/processed/mesh_elderly.csv.gz")
        df = df[df.pref_code.isin(MESH_PREFS)].reset_index(drop=True)
        df["pref"] = df.pref_code.astype(str).str.zfill(2)
        return df

    @cached_property
    def mesh_tree(self) -> cKDTree:
        return cKDTree(_project(self.mesh.lat.values, self.mesh.lon.values))

    @cached_property
    def pref_growth(self) -> dict[str, tuple[float, float]]:
        """県別 65歳以上人口（2020, 2025）。系統Bの2020→2025補正と同じ集計。"""
        keys = ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
        out: dict[str, list[float]] = {}
        with gzip.open(HVD / "data/processed/municipalities_age5.json.gz", "rt", encoding="utf-8") as f:
            for m in json.load(f):
                acc = out.setdefault(m["pref_code"], [0.0, 0.0])
                acc[0] += sum((m.get("ages_2020") or {}).get(k, 0) for k in keys)
                acc[1] += sum((m.get("ages") or {}).get(k, 0) for k in keys)
        return {k: (v[0], v[1]) for k, v in out.items()}

    @cached_property
    def munis(self) -> pd.DataFrame:
        """市区町村（代表点つき）の75歳以上 2020・2025。地域の高齢化トレンド用。"""
        rows = []
        with gzip.open(HVD / "data/processed/municipalities_age5.json.gz", "rt", encoding="utf-8") as f:
            for m in json.load(f):
                if not m.get("lat"):
                    continue
                a25, a20 = m.get("ages") or {}, m.get("ages_2020") or {}
                k75 = ["75-79", "80-84", "85-89", "90+"]
                rows.append(
                    {
                        "code": m["code"],
                        "pref": m["pref"],
                        "name": m["name"],
                        "lat": m["lat"],
                        "lon": m["lon"],
                        "e75_2020": sum(a20.get(k, 0) for k in k75),
                        "e75_2025": sum(a25.get(k, 0) for k in k75),
                    }
                )
        return pd.DataFrame(rows)

    @cached_property
    def facilities(self) -> pd.DataFrame:
        df = pd.read_csv(HVD / "data/processed/facilities.csv.gz")
        return df[df.pref.isin(["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "山梨県"])].dropna(
            subset=["lat", "lon"]
        ).reset_index(drop=True)

    @cached_property
    def fac_tree(self) -> cKDTree:
        return cKDTree(_project(self.facilities.lat.values, self.facilities.lon.values))

    @cached_property
    def hospital_weight(self) -> dict[str, float]:
        d = json.loads((HCT / "data/processed/hospital_visit_weights.json").read_text(encoding="utf-8"))
        return {k: float(v["hospital_weight_vs_clinic"]) for k, v in d["prefectures"].items()}

    @cached_property
    def competitors(self) -> pd.DataFrame:
        """在支診・在支病（厚生局名簿 2026-06）。座標は医療情報ネット突合＋JMAP点データで補完。"""
        latest = PROCESSED / "zaishishin_latest.csv.gz"  # update_zaishishin.py が作る最新版
        z = pd.read_csv(latest if latest.exists() else HVD / "data/processed/zaishishin.csv.gz")
        z["medical_code"] = pd.to_numeric(z.medical_code, errors="coerce").astype("Int64").astype(str)
        fp = pd.DataFrame(
            json.loads((HCT / "data/processed/facility_points.json").read_text(encoding="utf-8"))["facilities"]
        )
        fp["a"] = fp.address.map(_norm_addr)
        fp["n"] = fp.name.map(_norm_name)
        by_a = fp.drop_duplicates("a", keep=False).set_index("a")
        by_n = fp.drop_duplicates("n", keep=False).set_index("n")
        z["coord_source"] = np.where(z.lat.notna(), "医療情報ネット", "")
        for i, r in z[z.lat.isna()].iterrows():
            a, n = _norm_addr(r.address), _norm_name(r["name"])
            hit = None
            if a in by_a.index:
                hit = by_a.loc[a]
            elif n in by_n.index and str(by_n.loc[n].municipality) in str(r.address):
                hit = by_n.loc[n]
            if hit is not None:
                z.at[i, "lat"], z.at[i, "lon"] = hit.lat, hit.lon
                z.at[i, "coord_source"] = "JMAP突合"
        # それでも無い分は国土地理院 住所検索の結果（build_extra_datasets.py が作るキャッシュ）
        gsi_path = PROCESSED / "zaishishin_gsi.json"
        if gsi_path.exists():
            gsi = json.loads(gsi_path.read_text(encoding="utf-8"))
            for i, r in z[z.lat.isna()].iterrows():
                hit = gsi.get(str(r.medical_code) + "|" + str(r.address))
                if hit:
                    z.at[i, "lat"], z.at[i, "lon"] = hit["lat"], hit["lon"]
                    z.at[i, "coord_source"] = "国土地理院"
        z["pref"] = z.pref_code.astype(str).str.zfill(2)
        z["own_group"] = z.name.str.contains(OWN_GROUP_PATTERN)
        cls = z.zaishi_class.fillna("").map(lambda x: unicodedata.normalize("NFKC", x))  # 名簿は全角数字
        is_hosp = z.kind.str.contains("病院")
        enhanced = cls.str.contains("1|2")
        hw = z.pref_name.map(self.hospital_weight).fillna(1.0)
        z["enhanced"] = enhanced
        z["is_hospital"] = is_hosp
        z["weight"] = np.where(
            is_hosp,
            hw * np.where(enhanced, 1.0, W_STANDARD_HOSPITAL_FACTOR),
            np.where(enhanced, W_ENHANCED_CLINIC, W_STANDARD_CLINIC),
        )
        # 座標が取れなかった分を県別に補正（座標あり件数で割り戻す）
        cov = z.groupby("pref").lat.apply(lambda s: s.notna().mean())
        z["coverage"] = z.pref.map(cov)
        return z

    @cached_property
    def comp_geo(self) -> pd.DataFrame:
        c = self.competitors
        return c[c.lat.notna() & ~c.own_group].reset_index(drop=True)

    @cached_property
    def comp_tree(self) -> cKDTree:
        return cKDTree(_project(self.comp_geo.lat.values, self.comp_geo.lon.values))

    def _points(self, name: str) -> pd.DataFrame:
        path = PROCESSED / name
        if not path.exists():
            return pd.DataFrame(columns=["name", "corp", "address", "lat", "lon"])
        df = pd.read_csv(path, dtype={"office_no": str})
        return df[~df.name.str.contains(OWN_GROUP_PATTERN, na=False)].reset_index(drop=True)

    @cached_property
    def cm_offices(self) -> pd.DataFrame:
        """居宅介護支援事業所（CM）。介護サービス情報公表 オープンデータ。"""
        return self._points("cm_offices.csv.gz")

    @cached_property
    def nursing(self) -> pd.DataFrame:
        """訪問看護ステーション。同上。"""
        return self._points("nursing_stations.csv.gz")

    @cached_property
    def cm_tree(self) -> cKDTree | None:
        c = self.cm_offices
        return cKDTree(_project(c.lat.values, c.lon.values)) if len(c) else None

    @cached_property
    def nursing_tree(self) -> cKDTree | None:
        c = self.nursing
        return cKDTree(_project(c.lat.values, c.lon.values)) if len(c) else None

    @cached_property
    def future(self) -> pd.DataFrame | None:
        """市区町村別 65/75/85歳以上の将来推計（2020〜2050、社人研 令和5年推計）＋代表座標。"""
        path = PROCESSED / "future_pop.csv.gz"
        if not path.exists():
            return None
        f = pd.read_csv(path, dtype={"code": str})
        wide = f.pivot_table(index="code", columns="year", values=["e65", "e75", "e85"])
        wide.columns = [f"{a}_{b}" for a, b in wide.columns]
        coords = self.munis.set_index("code")[["lat", "lon"]]
        return wide.join(coords, how="inner").reset_index()

    def _count_in_radius(self, tree, df, lat, lon, radius_km) -> pd.DataFrame:
        if tree is None:
            return df.iloc[0:0]
        idx = tree.query_ball_point(_project([lat], [lon])[0], radius_km + 0.5)
        sub = df.iloc[idx]
        return sub[haversine_km(lat, lon, sub.lat.values, sub.lon.values) <= radius_km]

    # --------------------------------------------------------------- metrics
    @cached_property
    def _rates(self) -> dict[str, np.ndarray]:
        """県コード → 年齢4区分×(総数, 居宅, 施設) の受療率行列。系統B patients_from_mesh_bands と同じ値。"""
        nat = json.loads((HVD / "data/processed/national_visit_rates.json").read_text(encoding="utf-8"))
        pref = json.loads((HVD / "data/processed/pref_visit_rates.json").read_text(encoding="utf-8"))
        def mat(mr):
            return np.array([[mr[b][k] for k in ("patient_rate_total", "patient_rate_home", "patient_rate_facility")] for b in BANDS])
        out = {"__national__": mat(nat["mesh_band_rates"])}
        for code, info in pref["prefectures"].items():
            out[code] = mat(info.get("mesh_band_rates") or nat["mesh_band_rates"])
        return out

    @cached_property
    def _constants(self) -> tuple[float, float]:
        c = json.loads((HVD / "data/processed/national_constants.json").read_text(encoding="utf-8"))
        return float(c.get("same_building_facility_fraction", 0.75)), float(c.get("facility_visit_rate_among_residents", 0.55))

    def _rate(self, pref: str) -> np.ndarray:
        return self._rates.get(pref, self._rates["__national__"])

    def _demand(
        self,
        by_pref: dict[str, np.ndarray],
        residents: float,
        rate_pref: str | None = None,
        growth_prefs: list[str] | None = None,
    ) -> dict:
        """県別の高齢者数 [e65, e75, e85, e95] → 需要。

        系統Bは圏内で最も高齢者の多い県の受療率を圏全体に当てていたが、
        県境で値が跳ねるため、ここでは県ごとにその県の受療率を当てて合算する。
        rate_pref を指定すると全域をその県の受療率で計算する（潜在需要用）。
        """
        gp = growth_prefs or list(by_pref)
        g20 = sum(self.pref_growth.get(p, (0, 0))[0] for p in gp)
        g25 = sum(self.pref_growth.get(p, (0, 0))[1] for p in gp)
        growth = max(0.9, min(1.25, g25 / g20)) if g20 else 1.0
        tot = np.zeros(3)
        bands_sum = np.zeros(4)
        for p, e in by_pref.items():
            bands = np.maximum(0.0, np.array([e[0] - e[1], e[1] - e[2], e[2] - e[3], e[3]])) * growth
            tot += bands @ self._rate(rate_pref or p)
            bands_sum += bands
        total, home_raw, fac_raw = tot
        elderly = float(bands_sum.sum())
        # 以下は系統B recommended_home_from_raw と同一
        sb_fac_frac, fac_visit_rate = self._constants
        facility_from_ndb = fac_raw * sb_fac_frac
        apartment = fac_raw * (1.0 - sb_fac_frac)
        facility_from_beds = residents * fac_visit_rate
        w_b = min(0.7, 0.3 + residents / max(elderly, 1) * 5) if residents > 0 else 0.2
        fac_true = min((1 - w_b) * facility_from_ndb + w_b * facility_from_beds, total)
        home = ((home_raw + apartment) + max(0.0, total - fac_true)) / 2.0
        return {
            "elderly_65": elderly,
            "elderly_75": float(bands_sum[1:].sum()),
            "elderly_85": float(bands_sum[2:].sum()),
            "visit_total": float(total),
            "home": float(home),
            "facility": float(fac_true),
        }

    @cached_property
    def _mesh_arr(self) -> dict[str, np.ndarray]:
        m = self.mesh
        return {
            "lat": m.lat.values,
            "lon": m.lon.values,
            "e": m[["elderly_65", "elderly_75", "elderly_85", "elderly_95"]].values.astype(float),
            "pop": m.pop_total.values.astype(float),
            "pref": m.pref.values,
        }

    def point(self, lat: float, lon: float, radius_km: float = RADIUS_KM, *, single_pref: bool = False) -> dict:
        """1地点の全指標。single_pref=True は系統Bと同じ「最多県の受療率を圏全体に適用」（検証用）。"""
        ma = self._mesh_arr
        q = _project([lat], [lon])[0]
        idx = np.asarray(self.mesh_tree.query_ball_point(q, radius_km + 0.8), dtype=int)
        if len(idx) == 0:
            return {}
        d = haversine_km(lat, lon, ma["lat"][idx], ma["lon"][idx])
        h = MESH_HALF_DIAG_KM
        w = np.clip((radius_km - (d - h)) / (2 * h), 0.0, 1.0)
        keep = w > 0
        idx, w = idx[keep], w[keep]
        if len(idx) == 0:
            return {}
        ew = ma["e"][idx] * w[:, None]
        prefs = ma["pref"][idx]
        by_pref = {p: ew[prefs == p].sum(axis=0) for p in np.unique(prefs)}
        pref = max(by_pref, key=lambda p: by_pref[p][0])
        pop = float((ma["pop"][idx] * w).sum())
        e65_2020 = float(ew[:, 0].sum())

        fidx = self.fac_tree.query_ball_point(q, radius_km + 0.5)
        fs = self.facilities.iloc[fidx]
        fs = fs[haversine_km(lat, lon, fs.lat.values, fs.lon.values) <= radius_km]
        residents = float(fs.residents_est.sum())

        if single_pref:
            dem = self._demand({pref: ew.sum(axis=0)}, residents, growth_prefs=list(by_pref))
        else:
            dem = self._demand(by_pref, residents)
        latent = self._demand(by_pref, residents, rate_pref=LATENT_BENCHMARK_PREF)

        cidx = self.comp_tree.query_ball_point(q, radius_km + 0.5)
        cs = self.comp_geo.iloc[cidx]
        cs = cs[haversine_km(lat, lon, cs.lat.values, cs.lon.values) <= radius_km]
        comp_units = float((cs.weight / cs.coverage).sum())

        mu = self.munis
        mm = mu[haversine_km(lat, lon, mu.lat.values, mu.lon.values) <= radius_km]
        g75 = float(mm.e75_2025.sum() / mm.e75_2020.sum()) if len(mm) and mm.e75_2020.sum() else float("nan")

        cms = self._count_in_radius(self.cm_tree, self.cm_offices, lat, lon, radius_km)
        nss = self._count_in_radius(self.nursing_tree, self.nursing, lat, lon, radius_km)
        e75 = dem["elderly_75"]
        fut = {}
        fu = self.future
        if fu is not None:
            fm = fu[haversine_km(lat, lon, fu.lat.values, fu.lon.values) <= radius_km]
            if len(fm) == 0:  # 圏内に代表点が無い場合は最寄りの市区町村
                fm = fu.iloc[[int(np.argmin(haversine_km(lat, lon, fu.lat.values, fu.lon.values)))]]
            for col, base, tgt in (
                ("e75_growth_25_35", "e75_2025", "e75_2035"),
                ("e75_growth_25_40", "e75_2025", "e75_2040"),
                ("e85_growth_25_35", "e85_2025", "e85_2035"),
                ("e85_growth_25_40", "e85_2025", "e85_2040"),
            ):
                fut[col] = float(fm[tgt].sum() / fm[base].sum()) if fm[base].sum() else float("nan")

        return {
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km,
            "pref": pref,
            "pop_total_2020": pop,
            "elderly_65": dem["elderly_65"],
            "elderly_75": dem["elderly_75"],
            "elderly_85": dem["elderly_85"],
            "aging_rate_2020": e65_2020 / pop if pop else float("nan"),
            "market_home": dem["home"],
            "market_facility": dem["facility"],
            "market_total": dem["visit_total"],
            "latent_home": latent["home"],
            "underserved_ratio": latent["home"] / dem["home"] if dem["home"] else float("nan"),
            "facility_count": int(len(fs)),
            "facility_residents": residents,
            "facility_capacity": float(fs.capacity.sum()),
            "competitors_n": float((1.0 / cs.coverage).sum()),
            "competitors_enhanced_n": float((cs.enhanced / cs.coverage).sum()),
            "competitor_units": comp_units,
            "competition_density": comp_units / dem["elderly_75"] * 1e4 if dem["elderly_75"] else float("nan"),
            "market_per_competitor": dem["home"] / comp_units if comp_units else float("nan"),
            "latent_per_competitor": latent["home"] / comp_units if comp_units else float("nan"),
            "e75_growth_20_25": g75,
            "cm_offices_n": int(len(cms)),
            "cm_per_10k75": len(cms) / e75 * 1e4 if e75 else float("nan"),
            "nursing_n": int(len(nss)),
            "nursing_per_10k75": len(nss) / e75 * 1e4 if e75 else float("nan"),
            **fut,
            # 2035年の潜在居宅需要（85歳以上の伸びで延長。居宅需要の大半は85歳以上のため）
            "latent_home_2035": latent["home"] * fut.get("e85_growth_25_35", 1.0),
        }

    # ------------------------------------------------------------ group overlap
    def mesh_owner(self, clinics: list[Clinic] | None = None, radius_km: float = RADIUS_KM) -> pd.DataFrame:
        """各メッシュを最寄りの自院に割り当てる（半径内のみ）。"""
        clinics = clinics or self.clinics
        m = self.mesh
        lat, lon = m.lat.values, m.lon.values
        dist = np.vstack([haversine_km(c.lat, c.lon, lat, lon) for c in clinics])  # (n_clinic, n_mesh)
        cover = dist <= radius_km
        n_cover = cover.sum(axis=0)
        owner = np.where(n_cover > 0, dist.argmin(axis=0), -1)
        return pd.DataFrame({"owner": owner, "n_cover": n_cover, "elderly_65": m.elderly_65.values})

    def exclusive_share(self, clinics: list[Clinic] | None = None, radius_km: float = RADIUS_KM) -> dict[str, dict]:
        """院ごとの 圏内高齢者のうち自院が最寄りの割合（排他率）と重複院数。"""
        clinics = clinics or self.clinics
        own = self.mesh_owner(clinics, radius_km)
        m = self.mesh
        out = {}
        for i, c in enumerate(clinics):
            d = haversine_km(c.lat, c.lon, m.lat.values, m.lon.values)
            inside = d <= radius_km
            tot = own.elderly_65.values[inside].sum()
            excl = own.elderly_65.values[inside & (own.owner.values == i)].sum()
            contested = own.elderly_65.values[inside & (own.n_cover.values >= 2)].sum()
            sib8 = sum(1 for o in clinics if o.id != c.id and haversine_km(c.lat, c.lon, o.lat, o.lon) <= radius_km)
            sib16 = sum(
                1 for o in clinics if o.id != c.id and haversine_km(c.lat, c.lon, o.lat, o.lon) <= SIBLING_RADIUS_KM
            )
            out[c.id] = {
                "exclusive_ratio": excl / tot if tot else float("nan"),
                "contested_ratio": contested / tot if tot else float("nan"),
                "siblings_8km": sib8,
                "siblings_16km": sib16,
            }
        return out
