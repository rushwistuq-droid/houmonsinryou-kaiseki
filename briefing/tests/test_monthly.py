"""月次成長曲線の当てはめ（合成データで検証。実データは機密のため使わない）。"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from briefing.wakasa_brief.monthly import fit_curve  # noqa: E402


class TestCurveFit(unittest.TestCase):
    def test_saturated_series_recovers_ceiling(self):
        t = np.arange(0, 60)
        y = 300 / (1 + np.exp(-0.15 * (t - 20)))
        f = fit_curve(t, y, "X", "居宅")
        self.assertAlmostEqual(f.K, 300, delta=10)
        self.assertEqual(f.status, "上限接近")

    def test_early_growth_is_not_called_saturated(self):
        t = np.arange(0, 18)
        y = 5 + 4 * t  # まだ直線的に伸びている
        f = fit_curve(t, y, "X", "居宅")
        self.assertEqual(f.status, "上限未見（成長継続中）")

    def test_flat_series_is_saturated(self):
        t = np.arange(0, 40)
        y = np.minimum(10 * t, 200).astype(float)
        f = fit_curve(t, y, "X", "居宅")
        self.assertEqual(f.status, "上限接近")

    def test_short_series(self):
        f = fit_curve(np.arange(5), np.arange(5) + 1, "X", "居宅")
        self.assertEqual(f.status, "データ不足")


if __name__ == "__main__":
    unittest.main()
