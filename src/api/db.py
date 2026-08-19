"""Shared SQLite access for the FastAPI server."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "nifty100.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params=None) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params or [])
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params=None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def table_counts() -> dict:
    tables = [
        "companies",
        "sectors",
        "profitandloss",
        "balancesheet",
        "cashflow",
        "analysis",
        "documents",
        "prosandcons",
        "stock_prices",
        "financial_ratios",
        "peer_groups",
        "market_cap",
        "peer_percentiles",
    ]
    out = {}
    for t in tables:
        try:
            out[t] = query_one(f"SELECT COUNT(*) AS c FROM {t}")["c"]
        except Exception:
            out[t] = None
    return out
