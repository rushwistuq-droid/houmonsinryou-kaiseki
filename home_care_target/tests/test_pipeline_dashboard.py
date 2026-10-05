"""Tests for pipeline resolve, dashboard, and actions."""

from __future__ import annotations

import unittest

from home_care_target.actions import build_action_plans, public_action_summary
from home_care_target.dashboard import build_dashboard, public_dashboard
from home_care_target.pipeline import analyze_clinic, resolve_clinic


class TestPipeline(unittest.TestCase):
    def test_resolve_alias(self):
        p = resolve_clinic("ひばりが丘")
        self.assertIn("ひばりが丘", p.name)

    def test_resolve_urawa(self):
        p = resolve_clinic("浦和")
        self.assertAlmostEqual(p.lat, 35.8788, places=3)

    def test_analyze_one_shot(self):
        a = analyze_clinic(resolve_clinic("市川"), actual_home=59, actual_facility=45)
        self.assertGreater(a.operational_kpi_home, 0)
        self.assertGreater(a.capacity_cap_home, 0)
        row = a.management_row()
        self.assertIn("operational_kpi_home", row)
        self.assertIn("fair_share_kpi_home", row)


class TestDashboardAndActions(unittest.TestCase):
    def test_dashboard_triad(self):
        dash = build_dashboard()
        self.assertGreaterEqual(dash["n_clinics"], 13)
        pub = public_dashboard(dash)
        for r in pub["rows"]:
            self.assertIn("operational_kpi_home", r)
            self.assertNotIn("actual_home", r)

    def test_actions_deprioritize_urawa(self):
        plans = build_action_plans(months=12)
        urawa = next(p for p in plans if p.alias == "浦和")
        self.assertTrue(urawa.ignore_for_priority)
        # 施設偏重院が上位に来る
        top = [p for p in plans if not p.ignore_for_priority][:3]
        self.assertTrue(any(p.home_mix_band == "施設偏重" for p in top))
        pub = public_action_summary(plans)
        self.assertNotIn('"actual_home"', str(pub))


if __name__ == "__main__":
    unittest.main()
