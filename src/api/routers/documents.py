"""Documents endpoint — annual report links with URL validity."""

import requests
from fastapi import APIRouter, HTTPException

from src.api.db import query, query_one

router = APIRouter(prefix="/companies", tags=["documents"])


def _url_valid(url: str) -> bool:
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


@router.get("/{ticker}/documents")
def company_documents(ticker: str):
    comp = query_one("SELECT company_id FROM companies WHERE upper(ticker) = ?", [ticker.upper()])
    if not comp:
        raise HTTPException(404, "Ticker not found")
    rows = query(
        "SELECT year, annual_report FROM documents WHERE company_id = ? ORDER BY year DESC",
        [comp["company_id"]],
    )
    return {
        "ticker": ticker.upper(),
        "documents": [
            {
                "year": r["year"],
                "url": r["annual_report"],
                "is_url_valid": _url_valid(r["annual_report"]),
            }
            for r in rows
        ],
    }
