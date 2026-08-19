"""Portfolio statistics endpoints."""

import sqlite3

import pandas as pd
from fastapi import APIRouter

from src.api.db import DB_PATH

router = APIRouter(tags=["portfolio"])

KPIS = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
]


@router.get("/portfolio/stats")
def portfolio_stats():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        latest = int(conn.execute("SELECT MAX(year) FROM financial_ratios").fetchone()[0])
        fr = pd.read_sql("SELECT * FROM financial_ratios WHERE year = ?", conn, params=[latest])
    finally:
        conn.close()
    out = {}
    for col in KPIS:
        s = pd.to_numeric(fr[col], errors="coerce").dropna()
        out[col] = {f"P{p}": round(s.quantile(p / 100), 3) for p in [10, 25, 50, 75, 90]}
        out[col]["Mean"] = round(s.mean(), 3)
        out[col]["Std"] = round(s.std(), 3)
    return out
