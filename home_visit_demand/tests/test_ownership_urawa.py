"""主担当マップ・浦和トラッキングのテスト。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from home_visit_demand.hq_analysis import ClinicInput  # noqa: E402
from home_visit_demand.ownership_map import (  # noqa: E402
    build_mesh_ownership,
    write_cluster_ownership_map,
)
from home_visit_demand.urawa_tracking import (  # noqa: E402
    build_urawa_tracking,
    format_urawa_tracking,
    expected_band_for_urawa,
)


class TestOwnershipAndUrawa(unittest.TestCase):
    def test_mitaka_cluster_ownership(self):
        clinics = [
            ClinicInput("shakujii", "石神井公園", 35.743, 139.601),
            ClinicInput("hibarigaoka", "ひばりが丘", 35.745, 139.538),
            ClinicInput("mitaka", "三鷹", 35.683, 139.559),
        ]
        summary, cells = build_mesh_ownership(clinics, radius_km=8.0)
        self.assertGreater(len(cells), 100)
        self.assertEqual(set(summary.exclusive_elderly), {"shakujii", "hibarigaoka", "mitaka"})
        self.assertGreater(sum(summary.exclusive_elderly.values()), 0)
        self.assertGreater(summary.contested_elderly, 0)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "map.html"
            write_cluster_ownership_map(clinics, out, radius_km=8.0)
            self.assertTrue(out.exists())
            self.assertIn("主担当", out.read_text(encoding="utf-8"))

    def test_urawa_ramp(self):
        data = {
            "months": [
                {"month": "2026-07", "actual_home_patients": 14, "actual_facility_patients": 0},
                {"month": "2026-09", "actual_home_patients": 40, "actual_facility_patients": 5},
            ]
        }
        points = build_urawa_tracking(data)
        self.assertEqual(len(points), 2)
        self.assertGreater(points[1].capture_8km_pct or 0, points[0].capture_8km_pct or 0)
        band = expected_band_for_urawa()
        text = format_urawa_tracking(points, band)
        self.assertIn("浦和", text)
        self.assertIn("2026-07", text)


if __name__ == "__main__":
    unittest.main()
