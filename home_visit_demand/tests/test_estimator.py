#!/usr/bin/env python3
"""推定ロジックの単体テスト（ネットワーク不要）。"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.estimator import (  # noqa: E402
    catchment_weight,
    estimate_from_point,
    haversine_km,
    load_json,
)


class TestGeo(unittest.TestCase):
    def test_haversine_tokyo_osaka(self):
        # 東京駅〜大阪駅おおよそ400km
        d = haversine_km(35.681236, 139.767125, 34.702485, 135.495951)
        self.assertTrue(390 < d < 420)

    def test_catchment_weight(self):
        self.assertEqual(catchment_weight(0, 8), 1.0)
        self.assertEqual(catchment_weight(9, 8), 0.0)
        self.assertAlmostEqual(catchment_weight(8, 8), 0.35, places=4)


class TestEstimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rates = load_json("national_visit_rates.json")
        cls.constants = load_json("national_constants.json")
        cls.munis = load_json("municipalities.json")

    def test_datasets_loaded(self):
        self.assertIn("age_bands", self.rates)
        self.assertGreater(len(self.munis), 1000)
        # 全国推計が社会医療統計（約100万）のオーダーに近いこと
        total = self.rates["national_totals"]["estimated_monthly_patients_total"]
        self.assertTrue(700_000 < total < 1_300_000)

    def test_tokorozawa_estimate(self):
        # 所沢市役所付近
        result = estimate_from_point(
            35.7996,
            139.4686,
            address="埼玉県所沢市",
            geocoded_name="所沢市テスト",
            radius_km=8.0,
            rates=self.rates,
            constants=self.constants,
            municipalities=self.munis,
        )
        self.assertGreater(result.demographics["elderly_65"], 50_000)
        self.assertGreater(result.visit_patients_total, 1000)
        self.assertGreater(result.recommended_home_patients, 500)
        self.assertLess(
            result.recommended_home_patients, result.visit_patients_total
        )
        # 居宅推計が総需要の一定割合
        share = result.recommended_home_patients / result.visit_patients_total
        self.assertTrue(0.2 < share < 0.8)

    def test_facility_override_increases_facility_residents(self):
        base = estimate_from_point(
            35.7996,
            139.4686,
            radius_km=8.0,
            rates=self.rates,
            constants=self.constants,
            municipalities=self.munis,
        )
        heavy = estimate_from_point(
            35.7996,
            139.4686,
            radius_km=8.0,
            facility_beds_override=20_000,
            rates=self.rates,
            constants=self.constants,
            municipalities=self.munis,
        )
        self.assertGreater(heavy.facility_residents_est, base.facility_residents_est)

    def test_age_rates_increase_with_age(self):
        bands = self.rates["age_bands"]
        self.assertLess(bands["65-69"]["patient_rate_total"], bands["75-79"]["patient_rate_total"])
        self.assertLess(bands["75-79"]["patient_rate_total"], bands["90+"]["patient_rate_total"])


if __name__ == "__main__":
    unittest.main()
