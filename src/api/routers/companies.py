"""Company data endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.api.db import query, query_one

router = APIRouter(prefix="/companies", tags=["companies"])
REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reports" / "tearsheets"


@router.get("")
def list_companies(
    sector: str | None = None,
    market_cap_category: str | None = None,
    search: str | None = None,
):
    sql = (
        "SELECT company_id, ticker, company_name, broad_sector, sub_sector, "
        "roe_percentage AS roe_pct, roce_percentage AS roce_pct, "
        "market_cap_category, market_cap_crore FROM companies WHERE 1=1"
    )
    params = []
    if sector:
        sql += " AND broad_sector = ?"
        params.append(sector)
    if market_cap_category:
        sql += " AND market_cap_category = ?"
        params.append(market_cap_category)
    if search:
        sql += " AND (upper(ticker) LIKE ? OR upper(company_name) LIKE ?)"
        params += [f"%{search.upper()}%", f"%{search.upper()}%"]
    sql += " ORDER BY ticker"
    return query(sql, params)


@router.get("/{ticker}")
def company_profile(ticker: str):
    comp = query_one("SELECT * FROM companies WHERE upper(ticker) = ?", [ticker.upper()])
    if not comp:
        raise HTTPException(404, "Ticker not found")
    latest = query_one(
        "SELECT * FROM financial_ratios WHERE company_id = ? " "ORDER BY year DESC LIMIT 1",
        [comp["company_id"]],
    )
    return {"company": comp, "latest_year_kpis": latest}


def _year_filter(from_year, to_year):
    cond, params = "", []
    if from_year:
        cond += " AND year >= ?"
        params.append(int(from_year))
    if to_year:
        cond += " AND year <= ?"
        params.append(int(to_year))
    return cond, params


def _ticker_or_404(ticker: str) -> int:
    cid = query_one("SELECT company_id FROM companies WHERE upper(ticker) = ?", [ticker.upper()])
    if not cid:
        raise HTTPException(404, "Ticker not found")
    return cid["company_id"]


@router.get("/{ticker}/pl")
def company_pl(ticker: str, from_year: int | None = None, to_year: int | None = None):
    cid = _ticker_or_404(ticker)
    cond, params = _year_filter(from_year, to_year)
    return query(
        f"SELECT * FROM profitandloss WHERE company_id = ?{cond} ORDER BY year",
        [cid] + params,
    )


@router.get("/{ticker}/bs")
def company_bs(ticker: str, from_year: int | None = None, to_year: int | None = None):
    cid = _ticker_or_404(ticker)
    cond, params = _year_filter(from_year, to_year)
    return query(
        f"SELECT * FROM balancesheet WHERE company_id = ?{cond} ORDER BY year",
        [cid] + params,
    )


@router.get("/{ticker}/cashflow")
def company_cashflow(ticker: str, from_year: int | None = None, to_year: int | None = None):
    cid = _ticker_or_404(ticker)
    cond, params = _year_filter(from_year, to_year)
    return query(
        f"SELECT * FROM cashflow WHERE company_id = ?{cond} ORDER BY year",
        [cid] + params,
    )


@router.get("/{ticker}/ratios")
def company_ratios(ticker: str, year: int | None = None):
    cid = _ticker_or_404(ticker)
    if year:
        return query(
            "SELECT * FROM financial_ratios WHERE company_id = ? AND year = ?",
            [cid, year],
        )
    return query("SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year", [cid])


@router.get("/{ticker}/tearsheet")
def company_tearsheet(ticker: str):
    path = REPORTS_DIR / f"{ticker.upper()}_tearsheet.pdf"
    if not path.exists():
        raise HTTPException(404, "Tearsheet not found")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=f"{ticker.upper()}_tearsheet.pdf",
    )
