"""CAGR Engine — growth metrics with edge case handling.

Handles: NORMAL (positive+positive), DECLINE_TO_LOSS (positive+negative),
TURNAROUND (negative+positive), BOTH_NEGATIVE, ZERO_BASE, INSUFFICIENT_DATA.
"""

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def compute_cagr(start_value: float, end_value: float, n: int):
    """Standalone CAGR. Returns (value, flag).  Kept for unit-test compatibility."""
    if n <= 0:
        return None, None
    if start_value == 0:
        return None, "ZERO_BASE"
    if start_value > 0 and end_value > 0:
        cagr = ((end_value / start_value) ** (1 / n) - 1) * 100
        return round(cagr, 2), None
    elif start_value > 0 and end_value < 0:
        return None, "DECLINE_TO_LOSS"
    elif start_value < 0 and end_value > 0:
        return None, "TURNAROUND"
    else:
        return None, "BOTH_NEGATIVE"


class CAGRCalculator:
    def __init__(self, db_path="db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")

    def _cagr(self, start_val, end_val, years) -> dict:
        if start_val is None or end_val is None:
            return {"value": None, "flag": "INSUFFICIENT_DATA"}

        if abs(start_val) < 1e-12:
            return {"value": None, "flag": "ZERO_BASE"}

        if years <= 0:
            return {"value": None, "flag": "INSUFFICIENT_DATA"}

        if start_val > 0 and end_val > 0:
            cagr_val = ((end_val / start_val) ** (1.0 / years) - 1) * 100
            return {"value": round(cagr_val, 2), "flag": "NORMAL"}

        if start_val > 0 and end_val < 0:
            return {"value": None, "flag": "DECLINE_TO_LOSS"}

        if start_val < 0 and end_val > 0:
            return {"value": None, "flag": "TURNAROUND"}

        if start_val < 0 and end_val < 0:
            cagr_val = ((abs(end_val) / abs(start_val)) ** (1.0 / years) - 1) * 100
            return {"value": round(cagr_val, 2), "flag": "BOTH_NEGATIVE"}

        return {"value": None, "flag": "INSUFFICIENT_DATA"}

    def compute_company(self, company_id, metric="revenue"):
        metric_map = {
            "revenue": "total_revenue",
            "pat": "net_profit",
            "eps": "eps",
        }

        col = metric_map.get(metric, metric)
        df = pd.read_sql_query(
            text(
                "SELECT year, {} FROM profitandloss "
                "WHERE company_id = :cid ORDER BY year ASC".format(col)
            ),
            self.engine,
            params={"cid": company_id},
        )

        if df.empty or col not in df.columns:
            return {metric: {}}

        df = df.dropna(subset=[col])
        if df.empty:
            return {metric: {}}

        years = df["year"].tolist()
        values = df[col].tolist()

        result = {}
        for window_name, window_size in [("3y", 3), ("5y", 5), ("10y", 10)]:
            if len(years) < window_size + 1:
                result[window_name] = {"value": None, "flag": "INSUFFICIENT_DATA"}
                continue

            start_val = values[-(window_size + 1)]
            end_val = values[-1]
            actual_years = years[-1] - years[-(window_size + 1)]
            if actual_years <= 0:
                actual_years = window_size

            result[window_name] = self._cagr(start_val, end_val, actual_years)

        return {metric: result}

    def compute_all(self):
        companies = pd.read_sql_query(
            text("SELECT company_id FROM companies"), self.engine
        )

        all_results = []
        for _, row in companies.iterrows():
            cid = int(row["company_id"])
            for metric in ["revenue", "pat", "eps"]:
                res = self.compute_company(cid, metric)
                metric_data = res.get(metric, {})
                for window, info in metric_data.items():
                    all_results.append(
                        {
                            "company_id": cid,
                            "year": None,
                            "analysis_type": "CAGR",
                            "metric_name": f"cagr_{metric}_{window}",
                            "metric_value": info.get("value"),
                            "description": info.get("flag"),
                        }
                    )

        result_df = pd.DataFrame(all_results)
        if not result_df.empty:
            self._store_results(result_df)
        return result_df

    def _store_results(self, df: pd.DataFrame):
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM analysis WHERE analysis_type = 'CAGR'")
            )
        df.to_sql("analysis", self.engine, if_exists="append", index=False)

    def export(self, path="output/cagr_results.csv"):
        df = self.compute_all()
        if df.empty:
            print("[CAGR] No results to export.")
            return

        companies = pd.read_sql_query(
            text("SELECT company_id, ticker FROM companies"), self.engine
        )
        ticker_map = dict(
            zip(companies["company_id"], companies["ticker"])
        )

        export_rows = []
        for _, row in df.iterrows():
            cid = row["company_id"]
            mn = row["metric_name"]
            parts = mn.replace("cagr_", "", 1).rsplit("_", 1)
            metric = "_".join(parts[:-1]) if len(parts) >= 2 else mn
            window = parts[-1] if len(parts) >= 2 else mn

            export_rows.append(
                {
                    "company_id": cid,
                    "ticker": ticker_map.get(cid, ""),
                    "metric": metric,
                    "window": window,
                    "cagr_value": row["metric_value"],
                    "flag": row["description"],
                }
            )

        export_df = pd.DataFrame(export_rows)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        export_df.to_csv(path, index=False)
        print(f"[CAGR] Exported {len(export_df)} rows to {path}")
        return export_df


if __name__ == "__main__":
    calc = CAGRCalculator()
    calc.export()
