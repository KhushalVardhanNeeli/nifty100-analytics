"""CAGR Engine — growth metrics with all six edge-case handlers.

Edge cases (per spec):
  * Positive -> Positive : compute normally (flag = None)
  * Positive -> Negative : None + DECLINE_TO_LOSS
  * Negative -> Positive : None + TURNAROUND
  * Negative -> Negative : None + BOTH_NEGATIVE
  * Zero base            : None + ZERO_BASE
  * < n years of data    : None + INSUFFICIENT
"""

import os
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

WINDOWS = (3, 5, 10)
METRICS = ("revenue", "pat", "eps")


def compute_cagr(start_value: float, end_value: float, n: int) -> Tuple[Optional[float], Optional[str]]:
    """Compute CAGR using ((end/start)^(1/n) - 1) * 100.

    Returns (value, flag). value is None for every edge case; flag names the case.
    """
    if start_value is None or end_value is None:
        return None, "INSUFFICIENT"
    if n is None or n <= 0:
        return None, "INSUFFICIENT"
    if start_value == 0:
        return None, "ZERO_BASE"
    if start_value > 0 and end_value > 0:
        cagr = ((end_value / start_value) ** (1.0 / n) - 1) * 100
        return round(cagr, 2), None
    if start_value > 0 and end_value < 0:
        return None, "DECLINE_TO_LOSS"
    if start_value < 0 and end_value > 0:
        return None, "TURNAROUND"
    if start_value < 0 and end_value < 0:
        return None, "BOTH_NEGATIVE"
    return None, "INSUFFICIENT"


def compute_trailing_windows(years, values, windows=WINDOWS):
    """Compute trailing CAGR for each window, ending at the latest year.

    `years` and `values` are aligned, sorted ascending. Returns a dict of
    window (int) -> (value, flag).
    """
    result = {}
    years = list(years)
    values = list(values)
    for w in windows:
        if len(values) < w + 1:
            result[w] = (None, "INSUFFICIENT")
            continue
        start_val = values[-(w + 1)]
        end_val = values[-1]
        result[w] = compute_cagr(start_val, end_val, w)
    return result


class CAGRCalculator:
    """Computes revenue/PAT/EPS CAGR windows from the profitandloss table."""

    def __init__(self, db_path: str = "db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")

    def company_series(self, company_id: int) -> dict:
        df = pd.read_sql_query(
            text("SELECT year, sales, net_profit, eps FROM profitandloss "
                 "WHERE company_id = :cid ORDER BY year ASC"),
            self.engine, params={"cid": company_id},
        )
        return df

    def compute_company(self, company_id: int) -> dict:
        """Return {metric: {window: (value, flag)}} for the latest year."""
        df = self.company_series(company_id)
        out = {}
        if df.empty:
            return out
        col_map = {"revenue": "sales", "pat": "net_profit", "eps": "eps"}
        for metric, col in col_map.items():
            if col not in df.columns:
                out[metric] = {}
                continue
            sub = df[["year", col]].dropna(subset=[col])
            if sub.empty:
                out[metric] = {}
                continue
            out[metric] = compute_trailing_windows(sub["year"], sub[col])
        return out

    def compute_all(self) -> pd.DataFrame:
        """Return one row per (company_id, metric, window) -> value, flag."""
        companies = pd.read_sql_query(text("SELECT company_id FROM companies"), self.engine)
        rows = []
        for _, r in companies.iterrows():
            cid = int(r["company_id"])
            per_metric = self.compute_company(cid)
            for metric in METRICS:
                windows = per_metric.get(metric, {})
                for w in WINDOWS:
                    value, flag = windows.get(w, (None, "INSUFFICIENT"))
                    rows.append({
                        "company_id": cid, "metric": metric, "window": w,
                        "value": value, "flag": flag,
                    })
        return pd.DataFrame(rows)


if __name__ == "__main__":
    calc = CAGRCalculator()
    df = calc.compute_all()
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    df.to_csv(os.path.join(OUTPUT_DIR, "cagr_results.csv"), index=False)
    print(f"[CAGR] Exported {len(df)} rows to output/cagr_results.csv")
