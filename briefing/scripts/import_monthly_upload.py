#!/usr/bin/env python3
"""院から届いた月次 Excel（左に患者数、右に新規・終了）を機密 CSV に変換する。

    python3 briefing/scripts/import_monthly_upload.py analysis/confidential/raw/monthly_upload_YYYY-MM-DD.xlsx

出力（どちらも Git 管理外）:
  analysis/confidential/monthly_patients.csv  院別の月末患者数（居宅＝総数−施設）
  analysis/confidential/monthly_flow.csv      院別の月内の新規・終了
既存の患者数 CSV と値が違う月は一覧を表示する（過去分の修正があった場合に気づけるように）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from briefing.wakasa_brief import monthly_flow as mf  # noqa: E402

CONF = ROOT / "analysis/confidential"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--dry-run", action="store_true", help="差分を表示するだけで書き込まない")
    args = ap.parse_args()

    stock, flow = mf.parse_upload(args.xlsx)
    print(f"患者数: {stock.month.min()}〜{stock.month.max()}  {stock.clinic.nunique()}院 {len(stock)}行")
    print(f"新規・終了: {flow.month.min()}〜{flow.month.max()}  {flow.clinic.nunique()}院 {len(flow)}行")

    old_path = CONF / "monthly_patients.csv"
    if old_path.exists():
        old = mf.load(old_path)
        m = stock.merge(old, on=["clinic", "month"], how="inner", suffixes=("", "_old"))
        diff = m[(m.home_patients != m.home_patients_old) | (m.facility_patients != m.facility_patients_old)]
        print(f"既存の患者数との差: {len(diff)}か月")
        if len(diff):
            print(diff[["clinic", "month", "home_patients", "home_patients_old", "facility_patients", "facility_patients_old"]].to_string(index=False))

    gaps = mf.reconcile(flow, stock)
    print(f"患者数の増減と（新規−終了）が{mf.RECONCILE_TOL}人超ずれる月: {len(gaps)}")
    if args.dry_run:
        return
    stock.assign(month=stock.month.astype(str)).to_csv(old_path, index=False)
    flow.assign(month=flow.month.astype(str)).to_csv(CONF / "monthly_flow.csv", index=False)
    print(f"書き込み: {old_path}, {CONF / 'monthly_flow.csv'}")


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
