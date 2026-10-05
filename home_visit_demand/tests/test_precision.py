"""高精度推定のテスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.precision import (  # noqa: E402
    estimate_precision,
    mesh_intersection_weight,
)
from home_visit_demand.estimator import load_json  # noqa: E402


class TestPrecision(unittest.TestCase):
    def test_mesh_weight(self):
        self.assertEqual(mesh_intersection_weight(0, 8), 1.0)
        self.assertEqual(mesh_intersection_weight(20, 8), 0.0)
        self.assertTrue(0 < mesh_intersection_weight(8.0, 8.0) < 1)

    def test_pref_rates_exist(self):
        prefs = load_json("pref_visit_rates.json")
        self.assertEqual(len(prefs["prefectures"]), 47)
        tokyo = prefs["prefectures"]["13"]
        self.assertIn("intensity_vs_national", tokyo)
        self.assertTrue(0.3 < tokyo["intensity_vs_national"] < 3.0)

    def test_tokorozawa_precision(self):
        r = estimate_precision(35.805, 139.455, address="所沢テスト", radius_km=8.0)
        self.assertGreater(r.mesh_count, 100)
        self.assertGreater(r.demographics["elderly_65"], 30_000)
        self.assertGreater(r.recommended_home_patients, 200)
        self.assertLess(r.recommended_home_patients, r.visit_patients_total)
        self.assertGreater(r.facility_summary["facility_count"], 10)
        # 居宅は施設より小さいか同程度が都市部以外では多いが、比率は妥当範囲
        self.assertTrue(0.15 < r.recommended_home_patients / r.visit_patients_total < 0.85)

    def test_constants_same_building_split(self):
        c = load_json("national_constants.json")
        self.assertIn("same_building_facility_fraction", c)
        self.assertTrue(0.3 < c["same_building_facility_fraction"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
