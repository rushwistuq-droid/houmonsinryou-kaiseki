"""本部向け分析（重複除去・期待シェア帯・感度）のテスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.hq_analysis import (  # noqa: E402
    ClinicInput,
    analyze_mesh_overlap,
    capture_vs_band,
    density_tier_for_elderly,
    run_hq_pipeline,
    run_radius_sensitivity,
)


class TestHQAnalysis(unittest.TestCase):
    def test_density_tiers(self):
        self.assertEqual(density_tier_for_elderly(600_000)["tier"], "超稠密")
        self.assertEqual(density_tier_for_elderly(400_000)["tier"], "稠密")
        self.assertEqual(density_tier_for_elderly(280_000)["tier"], "準稠密")
        self.assertEqual(density_tier_for_elderly(100_000)["tier"], "郊外〜中密度")

    def test_capture_vs_band(self):
        self.assertEqual(capture_vs_band(1.0, 2.0, 5.0), "below")
        self.assertEqual(capture_vs_band(3.0, 2.0, 5.0), "within")
        self.assertEqual(capture_vs_band(8.0, 2.0, 5.0), "above")
        self.assertEqual(capture_vs_band(None, 2.0, 5.0), "n/a")

    def test_overlap_union_less_than_naive(self):
        # 本院と所沢は近接 → 重複が大きい
        clinics = [
            ClinicInput("honin", "本院", 35.805, 139.455),
            ClinicInput("tokorozawa", "所沢", 35.799, 139.472),
        ]
        summary, per = analyze_mesh_overlap(clinics, radius_km=8.0)
        self.assertLess(summary.union_elderly_65, summary.naive_sum_elderly_65)
        self.assertGreater(summary.overlap_pct_of_naive, 10.0)
        self.assertGreater(summary.union_market_home, 1000)
        self.assertIn("honin", per)
        self.assertGreater(per["honin"]["exclusive_market_home"], 0)

    def test_sensitivity_radii_monotonic(self):
        clinics = [ClinicInput("honin", "本院", 35.805, 139.455, actual_home_patients=509)]
        rows = run_radius_sensitivity(clinics, [5.0, 8.0, 10.0])
        by = rows[0].by_radius
        self.assertLessEqual(by["5"]["market_home"], by["8"]["market_home"])
        self.assertLessEqual(by["8"]["market_home"], by["10"]["market_home"])
        # 半径拡大で獲得率は下がる（実績固定）
        self.assertGreaterEqual(by["5"]["home_capture_pct"], by["8"]["home_capture_pct"])

    def test_pipeline_two_clinics(self):
        clinics = [
            ClinicInput(
                "honin", "本院", 35.805, 139.455,
                actual_home_patients=509, actual_facility_patients=1148,
            ),
            ClinicInput(
                "urawa", "浦和", 35.880526, 139.641896,
                actual_home_patients=14, actual_facility_patients=0,
            ),
        ]
        result = run_hq_pipeline(clinics, primary_radius_km=8.0, sensitivity_radii=[5.0, 8.0])
        self.assertEqual(len(result.clinics), 2)
        self.assertEqual(len(result.facility_kpi), 2)
        self.assertIn("market_home", result.definitions)
        fac = result.facility_kpi[0]
        self.assertEqual(fac["contract_facility_patients"], 1148)
        # 施設パネル構成比は契約側のみ
        self.assertAlmostEqual(fac["facility_share_of_panel_pct"], 100.0 * 1148 / (1148 + 509), places=0)


if __name__ == "__main__":
    unittest.main()
