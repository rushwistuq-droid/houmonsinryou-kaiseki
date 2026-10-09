"""エンジンが系統Bの公表値を再現できるか（旧座標・単一県モードで比較）。"""

import json
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from briefing.wakasa_brief.engine import Engine  # noqa: E402


class TestReproducesSystemB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = Engine()
        cls.B = {c["id"]: c for c in json.loads((ROOT / "home_visit_demand/examples/wakasa_hq_pipeline.json").read_text())["clinics"]}
        tpl = yaml.safe_load((ROOT / "home_visit_demand/data/templates/actuals_2026-07.example.yaml").read_text())
        cls.old = {c["id"]: (c["lat"], c["lon"]) for c in tpl["clinics"]}

    def test_market_home_within_half_percent(self):
        for cid, (lat, lon) in self.old.items():
            p = self.E.point(lat, lon, 8.0, single_pref=True)  # 系統Bは半径8km
            b = self.B[cid]
            self.assertAlmostEqual(p["elderly_65"], b["elderly_65"], delta=1.0, msg=cid)
            self.assertLess(abs(p["market_home"] / b["market_home"] - 1), 0.005, msg=cid)

    def test_latent_equals_market_in_tokyo_core(self):
        p = self.E.point(35.6812, 139.7671)  # 東京駅（8km圏はほぼ東京都）
        self.assertLess(abs(p["underserved_ratio"] - 1), 0.02)

    def test_saitama_is_underserved(self):
        p = self.E.point(35.8617, 139.6455)  # さいたま市浦和区
        self.assertGreater(p["underserved_ratio"], 1.5)


class TestCompetitors(unittest.TestCase):
    def test_enhanced_flag_detected(self):
        c = Engine().competitors
        # 名簿の類型は全角（支援診１・２ア等）。機能強化型が一定数検出されること
        self.assertGreater(c.enhanced.sum(), 1000)
        self.assertTrue(c[c.zaishi_class == "支援診３"].enhanced.eq(False).all())

    def test_own_group_excluded(self):
        E = Engine()
        self.assertFalse(E.comp_geo.name.str.contains("わかさクリニック").any())


if __name__ == "__main__":
    unittest.main()


class TestRadius(unittest.TestCase):
    def test_engine_radius_is_used_by_default(self):
        E6, E8 = Engine(radius_km=6.0), Engine(radius_km=8.0)
        c = E6.clinics[0]
        p6, p8 = E6.point(c.lat, c.lon), E8.point(c.lat, c.lon)
        self.assertEqual(p6["radius_km"], 6.0)
        # 面積比 (6/8)^2 ≈ 0.56 前後（人口分布で多少ずれる）
        self.assertLess(p6["elderly_65"] / p8["elderly_65"], 0.75)
        self.assertGreater(p6["elderly_65"] / p8["elderly_65"], 0.35)
