"""Sector endpoints."""

import sqlite3

from fastapi import APIRouter, HTTPException

from src.api.db import DB_PATH, query_one

router = APIRouter(tags=["sectors"])


@router.get("/sectors")
def list_sectors():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        latest = int(conn.execute("SELECT MAX(year) FROM financial_ratios").fetchone()[0])
        cur = conn.execute(
            """SELECT c.broad_sector AS sector,
                      COUNT(*) AS company_count,
                      ROUND(AVG(fr.return_on_equity_pct),2) AS median_roe,
                      ROUND(AVG(fr.debt_to_equity),2) AS median_de
               FROM companies c
               LEFT JOIN financial_ratios fr
                 ON c.company_id = fr.company_id AND fr.year = ?
               WHERE c.broad_sector IS NOT NULL
               GROUP BY c.broad_sector ORDER BY c.broad_sector""",
            (latest,),
        )
        sectors = [dict(r) for r in cur.fetchall()]
        # median PE from market_cap
        for s in sectors:
            s["median_pe"] = conn.execute(
                "SELECT ROUND(AVG(mc.pe_ratio),2) FROM market_cap mc "
                "JOIN companies c ON c.company_id=mc.company_id "
                "WHERE mc.year=? AND c.broad_sector=?",
                (latest, s["sector"]),
            ).fetchone()[0]
        return sectors
    finally:
        conn.close()


@router.get("/sectors/{sector}/companies")
def sector_companies(sector: str):
    check = query_one("SELECT COUNT(*) AS c FROM companies WHERE broad_sector = ?", [sector])
    if not check or check["c"] == 0:
        raise HTTPException(404, "Unknown sector")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        latest = int(conn.execute("SELECT MAX(year) FROM financial_ratios").fetchone()[0])
        cur = conn.execute(
            """SELECT c.ticker, c.company_name, c.sub_sector,
                      fr.return_on_equity_pct, fr.return_on_capital_employed_pct,
                      fr.net_profit_margin_pct, fr.debt_to_equity, fr.revenue_cagr_5yr
               FROM companies c LEFT JOIN financial_ratios fr
                 ON c.company_id = fr.company_id AND fr.year = ?
               WHERE c.broad_sector = ? ORDER BY c.ticker""",
            (latest, sector),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
