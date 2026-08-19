"""Screener endpoint."""

from fastapi import APIRouter, HTTPException

from src.api.db import DB_PATH
from src.screener.engine import ScreenerEngine

router = APIRouter(tags=["screener"])


@router.get("/screener")
def screener(
    min_roe: float | None = None,
    max_de: float | None = None,
    min_fcf: float | None = None,
    sector: str | None = None,
    min_rev_cagr_5yr: float | None = None,
    min_pat_cagr_5yr: float | None = None,
    max_pe: float | None = None,
):
    try:
        engine = ScreenerEngine(db_path=str(DB_PATH))
        df = engine.load_data()
        df = engine.composite_score(df)
    except Exception as e:
        raise HTTPException(500, f"Screener data error: {e}")

    mask = None
    for col, val in [
        ("roe", min_roe),
        ("revenue_cagr_5y", min_rev_cagr_5yr),
        ("pat_cagr_5y", min_pat_cagr_5yr),
    ]:
        if val is not None:
            m = df[col].fillna(-1e18) >= val
            mask = m if mask is None else (mask & m)
    if min_fcf is not None:
        m = df["free_cash_flow"].fillna(-1e18) >= min_fcf
        mask = m if mask is None else (mask & m)
    if max_de is not None:
        fin = df["broad_sector"].fillna("").astype(str).str.lower().str.contains("financial")
        m = (df["debt_to_equity"].fillna(999) <= max_de) | fin
        mask = m if mask is None else (mask & m)
    if max_pe is not None:
        m = df["pe_ratio"].fillna(1e9) <= max_pe
        mask = m if mask is None else (mask & m)
    if sector:
        m = df["broad_sector"].fillna("") == sector
        mask = m if mask is None else (mask & m)

    if mask is not None:
        df = df[mask]
    df = df.sort_values("composite_score", ascending=False)
    cols = [
        "ticker",
        "company_name",
        "broad_sector",
        "roe",
        "roce",
        "net_profit_margin",
        "debt_to_equity",
        "free_cash_flow",
        "revenue_cagr_5y",
        "pat_cagr_5y",
        "pe_ratio",
        "composite_score",
    ]
    cols = [c for c in cols if c in df.columns]
    records = df[cols].to_dict("records")
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                rec[k] = None
    return records
