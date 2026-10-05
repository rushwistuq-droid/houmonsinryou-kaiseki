"""Tests for actuals YAML loader and public summary."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from home_care_target.actuals_compare import (
    ActualVsKpiRow,
    _parse_simple_actuals_yaml,
    load_actuals,
    rows_to_public_summary,
)
from home_care_target.wakasa_demo_data import CLINIC_ALIASES, CLINICS


SAMPLE = """
as_of: "2026-07"
clinics:
  - alias: ひばりが丘
    facility: 393
    home: 122
  - alias: 浦和
    facility: 0
    home: 14
"""


class TestActualsLoader(unittest.TestCase):
    def test_simple_yaml_parse(self):
        data = _parse_simple_actuals_yaml(SAMPLE)
        self.assertEqual(len(data["clinics"]), 2)
        self.assertEqual(data["clinics"][0]["home"], 122)

    def test_load_actuals_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.yaml"
            p.write_text(SAMPLE, encoding="utf-8")
            out = load_actuals(p)
            self.assertIn(CLINIC_ALIASES["ひばりが丘"], out)
            self.assertEqual(out[CLINIC_ALIASES["浦和"]]["home"], 14)

    def test_public_summary_hides_raw_counts(self):
        rows = [
            ActualVsKpiRow(
                clinic="わかさクリニック浦和",
                alias="浦和",
                actual_facility=0,
                actual_home=14,
                actual_total=14,
                actual_home_share=1.0,
                fair_share_kpi=28,
                operational_kpi=38,
                operational_stretch=50,
                growth_mode="early",
                home_mix_band="居宅寄り",
                home_shift_gap=0,
                gap_vs_operational=-24,
                attainment_vs_operational=0.37,
                competition_label="中",
                ignore_for_priority=True,
                status="開院初期（優先対象外）",
                physician_fte=1.0,
            )
        ]
        pub = rows_to_public_summary(rows)
        self.assertTrue(all(not k.startswith("actual_") for k in pub["clinics"][0]))
        self.assertEqual(pub["band_counts"]["開院初期（優先対象外）"], 1)

    def test_urawa_in_clinics(self):
        self.assertIn("わかさクリニック浦和", [c.name for c in CLINICS])


if __name__ == "__main__":
    unittest.main()
