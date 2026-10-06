"""月次解析（合成データで検証。実データは機密のため使わない）。"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from briefing.wakasa_brief import monthly_analysis as ma  # noqa: E402


def _frame():
    months = pd.period_range("2024-01", "2025-12", freq="M")
    rows = []
    for i, m in enumerate(months):
        rows.append({"clinic": "A", "month": m, "home_patients": 50 + 5 * i, "facility_patients": 200 - (60 if i >= 12 else 0)})
        rows.append({"clinic": "B", "month": m, "home_patients": 100, "facility_patients": 10 + (60 if i >= 12 else 0)})
    df = pd.DataFrame(rows)
    df["total_patients"] = df.home_patients + df.facility_patients
    return ma.add_months_open(df, {"A": "2023-06", "B": "2023-06"})


class TestMonthlyAnalysis(unittest.TestCase):
    def test_growth_trend_labels(self):
        g = ma.growth_table(_frame())
        self.assertEqual(g.loc["A", "home_trend"], "増加")
        self.assertEqual(g.loc["B", "home_trend"], "横ばい")

    def test_transfer_detected(self):
        df = _frame()
        sp = ma.detect_spikes(df)
        tr = ma.transfer_candidates(sp, {"A": "2023-06", "B": "2023-06"})
        self.assertEqual(len(tr), 1)
        self.assertEqual(tr.iloc[0]["month"], "2025-01")
        self.assertEqual(int(tr.iloc[0]["減少合計"]), -60)

    def test_forecast_trend_extension(self):
        fc = ma.forecast_12m(_frame())
        self.assertEqual(int(fc.loc["A", "trend_12m"]), 165 + 60)
        self.assertEqual(int(fc.loc["B", "trend_12m"]), 100)


if __name__ == "__main__":
    unittest.main()
