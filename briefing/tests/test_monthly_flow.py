"""新規・終了の解析（合成データで検証。実データは機密のため使わない）。"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from briefing.wakasa_brief import monthly_flow as mf  # noqa: E402


def _simulate(new, rate, start, months):
    """毎月 new 人が入り、患者の rate が終了する院の患者数とフロー。"""
    stock, rows = float(start), []
    for m in months:
        end = rate * stock
        stock = stock + new - end
        rows.append((m, new, end, stock))
    return rows


def _frames():
    months = pd.period_range("2024-01", "2025-12", freq="M")
    srows, frows = [], []
    # A: 均衡に到達済み・新規はエリアの大きさ並み / B: 均衡・新規が少ない / G: まだ伸びる / C: 均衡・終了が多い
    spec = {"A": (10, 0.05, 200), "B": (3, 0.05, 60), "G": (10, 0.05, 80), "C": (10, 0.09, 111), "D": (10, 0.05, 200)}
    for c, (new, rate, start) in spec.items():
        for m, n, e, s in _simulate(new, rate, start, months):
            srows.append({"clinic": c, "month": m, "home_patients": round(s), "facility_patients": 100})
            frows.append({"clinic": c, "month": m, "new_home": n, "end_home": round(e), "new_facility": 5, "end_facility": 5})
    stock, flow = pd.DataFrame(srows), pd.DataFrame(frows)
    diag = pd.DataFrame({
        "name": list(spec), "months_open": [60] * len(spec),
        "reach_target": [200, 200, 200, 120, 200], "penetration_of_target": [1.0, 0.3, 0.4, 0.9, 1.0],
    })
    return stock, flow, diag


class TestMonthlyFlow(unittest.TestCase):
    def test_equilibrium_and_causes(self):
        stock, flow, diag = _frames()
        ft = mf.flow_table(flow, stock)
        self.assertAlmostEqual(ft.loc["A", "eq_home"], 200, delta=8)
        self.assertGreater(ft.loc["G", "eq_ratio_home"], mf.EQ_GROWING)
        c = mf.classify(ft, diag, first_mover="D")
        self.assertEqual(c.loc["A", "flow_outlook"], "横ばい（均衡）")
        self.assertTrue(c.loc["A", "stall_cause"].startswith("A"))
        self.assertTrue(c.loc["B", "stall_cause"].startswith("B"))
        self.assertIn("C", c.loc["C", "stall_cause"])
        self.assertEqual(c.loc["G", "flow_outlook"], "まだ伸びる")
        self.assertEqual(c.loc["D", "stall_cause"], "（先行院）")

    def test_adjust_flow_removes_transfer_from_ends(self):
        _, flow, _ = _frames()
        ev = [{"month": "2025-03", "clinic": "A", "series": "facility", "delta": -40, "kind": "移管"}]
        flow.loc[(flow.clinic == "A") & (flow.month == pd.Period("2025-03", freq="M")), "end_facility"] = 45
        out = mf.adjust_flow(flow, ev)
        self.assertEqual(out.loc[(out.clinic == "A") & (out.month == pd.Period("2025-03", freq="M")), "end_facility"].iloc[0], 5)

    def test_reconcile_flags_gaps(self):
        stock, flow, _ = _frames()
        k = (stock.clinic == "B") & (stock.month >= pd.Period("2025-06", freq="M"))
        stock.loc[k, "home_patients"] -= 20  # 記録されていない一度きりの減少
        gaps = mf.reconcile(flow, stock)
        self.assertEqual(len(gaps[gaps.clinic == "B"]), 1)

    def test_parse_upload_layout(self):
        """左に患者数（年の無い見出し）、右に新規・終了（年月つき見出し）が並ぶ様式。"""
        months = [pd.Timestamp("2025-03-01"), pd.Timestamp("2025-02-01"), pd.Timestamp("2025-01-01")]
        header = [None, "日付", 45717, 45689, 45658, None, None, "時期", *months]
        rows = [header]
        for c in ("本院", "石神井"):
            stock = [["施設", 100, 98, 95], ["居宅", 50, 48, 45], ["居宅(がん医総)", 2, 2, 1], ["総数", 152, 148, None]]
            flow = [["施設新規", 5, 6, 4], ["居宅新規", 4, 5, None], ["施設終了", 3, 3, 2], ["居宅終了", 2, 2, 1]]
            for i in range(4):
                rows.append([c if i == 0 else None, *stock[i], None, c if i == 0 else None, *flow[i]])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.xlsx"
            pd.DataFrame(rows).to_excel(p, header=False, index=False)
            stock, flow = mf.parse_upload(p)
        self.assertEqual(set(stock.clinic), {"本院", "石神井公園"})
        s = stock.set_index(["clinic", "month"])
        self.assertEqual(s.loc[("本院", pd.Period("2025-03", freq="M")), "home_patients"], 52)
        # 総数が空欄の月は 施設＋居宅＋がん医総 で復元
        self.assertEqual(s.loc[("本院", pd.Period("2025-01", freq="M")), "total_patients"], 141)
        f = flow.set_index(["clinic", "month"])
        self.assertEqual(f.loc[("本院", pd.Period("2025-01", freq="M")), "new_home"], 0)  # 片方だけ空欄＝0人
        self.assertTrue(np.isfinite(f.new_facility).all())


if __name__ == "__main__":
    unittest.main()
