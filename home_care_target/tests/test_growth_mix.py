"""Tests for growth KPI, home mix, own-group exclusion, enhanced flags."""

from __future__ import annotations

import unittest

from home_care_target.facilities import (
    count_facilities_in_radius,
    is_own_group_facility,
    load_facility_points,
)
from home_care_target.growth import compute_growth_kpi, compute_home_mix_target
from home_care_target.pipeline import analyze_clinic, resolve_clinic
from home_care_target.referral import allocate_channel_quotas


class TestGrowthAndMix(unittest.TestCase):
    def test_mature_uses_increment(self):
        g = compute_growth_kpi(
            actual_home=50,
            actual_facility=50,
            fair_share_kpi=40,
            fair_share_floor=15,
            fair_share_stretch=60,
            capacity_cap_home=120,
            fte_cap_home=200,
            annual_increment=24,
        )
        self.assertEqual(g.mode, "mature")
        self.assertEqual(g.operational_kpi_home, 74)  # 50+24
        self.assertGreater(g.operational_kpi_home, g.fair_share_kpi)

    def test_home_mix_facility_heavy(self):
        m = compute_home_mix_target(actual_home=122, actual_facility=393)
        self.assertEqual(m.band, "施設偏重")
        self.assertGreater(m.shift_gap_to_target, 0)

    def test_home_mix_home_leaning(self):
        m = compute_home_mix_target(actual_home=335, actual_facility=142)
        self.assertEqual(m.band, "居宅寄り")
        self.assertEqual(m.shift_gap_to_target, 0)


class TestOwnGroupAndEnhanced(unittest.TestCase):
    def test_own_group_name(self):
        self.assertTrue(is_own_group_facility("医療法人 元気会 わかさクリニック府中"))
        self.assertFalse(is_own_group_facility("一般クリニック"))

    def test_exclude_own_group_from_count(self):
        pts = load_facility_points()
        # 府中付近
        with_own = count_facilities_in_radius(35.669, 139.477, 8.0, pts, exclude_own_group=False)
        without = count_facilities_in_radius(35.669, 139.477, 8.0, pts, exclude_own_group=True)
        self.assertGreaterEqual(with_own.clinics, without.clinics)
        self.assertGreaterEqual(without.excluded_own_group, 1)

    def test_enhanced_flags_loaded(self):
        pts = load_facility_points()
        enh = sum(1 for p in pts if p.enhanced)
        self.assertGreater(enh, 500)
        # known clinic analysis uses facility-level enhanced
        a = analyze_clinic(resolve_clinic("ひばりが丘"), actual_home=122, actual_facility=393)
        self.assertGreater(a.clinic_enhanced_est, 0)
        self.assertEqual(a.clinic_enhanced_est + a.clinic_standard_est, a.competitors_clinics)


class TestReferralAllocate(unittest.TestCase):
    def test_allocate(self):
        playbook = [
            {"channel": "居宅介護支援（CM）", "share": 0.5},
            {"channel": "病院退院調整", "share": 0.5},
        ]
        q = allocate_channel_quotas(10, playbook)
        self.assertAlmostEqual(q["cm"] + q["hospital"], 10.0)


class TestUrawaIgnored(unittest.TestCase):
    def test_urawa_ignore_flag(self):
        a = analyze_clinic(resolve_clinic("浦和"), actual_home=14, actual_facility=0)
        self.assertTrue(a.growth.ignore_for_priority)


if __name__ == "__main__":
    unittest.main()
