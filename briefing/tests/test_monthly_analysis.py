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

    def test_adjustment_removes_level_shift(self):
        df = _frame()
        adj = ma.apply_adjustments(df, [{"month": "2025-01", "clinic": "A", "series": "facility", "delta": -60, "kind": "移管"}])
        a = adj[adj.clinic == "A"].facility_patients
        self.assertTrue((a == 140).all())  # 段差が消えて一定
        self.assertTrue(ma.detect_spikes(adj[adj.clinic == "A"]).empty)
        # グループ合計用（集計修正のみ）では移管は補正しない
        same = ma.apply_adjustments(df, [{"month": "2025-01", "clinic": "A", "series": "facility", "delta": -60, "kind": "移管"}], kinds=("集計修正",))
        self.assertTrue(same.facility_patients.equals(df.facility_patients))

    def test_linear_spread_correction(self):
        df = _frame()
        adj = ma.apply_adjustments(df, [{"month": "2025-01", "clinic": "B", "series": "home", "delta": -12, "kind": "集計修正", "spread": "linear"}])
        b = adj[adj.clinic == "B"].set_index(adj[adj.clinic == "B"].month.astype(str)).home_patients
        self.assertEqual(b["2024-01"], 99)   # 最初の月はほぼ補正なし
        self.assertEqual(b["2024-12"], 88)   # 直前の月で全額
        self.assertEqual(b["2025-01"], 100)  # 修正後はそのまま

    def test_forecast_trend_extension(self):
        fc = ma.forecast_12m(_frame())
        self.assertEqual(int(fc.loc["A", "trend_12m"]), 165 + 60)
        self.assertEqual(int(fc.loc["B", "trend_12m"]), 100)


if __name__ == "__main__":
    unittest.main()
