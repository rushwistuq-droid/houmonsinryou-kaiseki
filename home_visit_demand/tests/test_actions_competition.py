"""アクションシート・外部競合のテスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.action_sheets import build_action_sheets  # noqa: E402
from home_visit_demand.competition import (  # noqa: E402
    adjust_share_for_external_competition,
    competition_metrics,
)
from home_visit_demand.dashboard import render_hq_dashboard  # noqa: E402
from home_visit_demand.hq_analysis import ClinicInput, run_hq_pipeline  # noqa: E402
from home_visit_demand.precision import DATA_DIR  # noqa: E402


class TestCompetitionAndActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA_DIR / "competitors_home.csv.gz").exists():
            import importlib.util

            path = ROOT / "scripts" / "build_competitors.py"
            spec = importlib.util.spec_from_file_location("build_competitors", path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader
            spec.loader.exec_module(mod)
            mod.build()
        if not (DATA_DIR / "zaishishin.csv.gz").exists():
            import importlib.util

            path = ROOT / "scripts" / "build_zaishishin.py"
            spec = importlib.util.spec_from_file_location("build_zaishishin", path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader
            spec.loader.exec_module(mod)
            mod.build()

    def test_competition_tokorozawa(self):
        m = competition_metrics(35.805, 139.455, 8.0, elderly_65=280_000)
        self.assertGreaterEqual(m["all_clinics_in_radius"], 100)
        # 在支診（厚生局）が主指標
        self.assertGreaterEqual(m.get("zaishishin_competitors", 0), 20)
        self.assertGreaterEqual(m["home_visit_competitors"], 20)
        self.assertIn("外部競合", m["external_competition_tier"])

    def test_external_share_adjust(self):
        low, high, notes = adjust_share_for_external_competition(
            3.0, 12.0, {"external_competition_tier": "外部競合・高", "home_visit_competitors": 30}
        )
        self.assertLess(low, 3.0)
        self.assertLess(high, 12.0)
        self.assertTrue(notes)

    def test_action_sheets_and_dashboard(self):
        clinics = [
            ClinicInput(
                "honin", "本院", 35.805, 139.455,
                actual_home_patients=509, actual_facility_patients=1148,
            ),
            ClinicInput(
                "ichikawa", "市川", 35.718, 139.915,
                actual_home_patients=59, actual_facility_patients=45,
            ),
            ClinicInput(
                "urawa", "浦和", 35.880526, 139.641896,
                actual_home_patients=14, actual_facility_patients=0,
            ),
        ]
        result = run_hq_pipeline(
            clinics, primary_radius_km=8.0, sensitivity_radii=[5.0, 8.0]
        )
        actions = build_action_sheets(result)
        by_id = {a.clinic_id: a for a in actions}
        self.assertEqual(by_id["urawa"].decision, "様子見")
        self.assertEqual(by_id["ichikawa"].decision, "やる")
        self.assertEqual(by_id["honin"].decision, "横展開")
        html = render_hq_dashboard(result)
        self.assertIn("本部ダッシュボード", html)
        self.assertIn("本院", html)
        self.assertIn(result.radius_policy["standard_km"], html)


if __name__ == "__main__":
    unittest.main()
