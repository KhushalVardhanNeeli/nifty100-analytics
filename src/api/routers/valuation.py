"""Valuation endpoints."""

from fastapi import APIRouter, HTTPException

from src.api.db import query, query_one

router = APIRouter(tags=["valuation"])


@router.get("/market-cap/{ticker}")
def market_cap_history(ticker: str):
    comp = query_one("SELECT company_id FROM companies WHERE upper(ticker) = ?", [ticker.upper()])
    if not comp:
        raise HTTPException(404, "Ticker not found")
    rows = query(
        "SELECT year, market_cap_crore, pe_ratio, pb_ratio, ev_ebitda, dividend_yield_pct "
        "FROM market_cap WHERE company_id = ? ORDER BY year",
        [comp["company_id"]],
    )
    return {"ticker": ticker.upper(), "history": rows}
