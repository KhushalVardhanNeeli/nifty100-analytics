from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import os

app = FastAPI(title="Nifty 100 Financial Analytics API", version="1.0.0")

# NOTE: Consider adding rate limiting middleware (e.g., slowapi) for production use.
# from slowapi import Limiter, _rate_limit_exceeded_handler
# from slowapi.util import get_remote_address
# limiter = Limiter(key_func=get_remote_address)
# app.state.limiter = limiter
# app.add_exception_handler(429, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "db/nifty100.db"


@contextmanager
def get_connection():
    """Context manager for SQLite database connections with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _fetch_company(conn: sqlite3.Connection, company_id: int) -> Dict[str, Any]:
    """Fetch a company row by id, or raise HTTP 404."""
    row = conn.execute(
        "SELECT * FROM companies WHERE company_id = ?", [company_id]
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Company with id {company_id} not found")
    return dict(row)


# ── Existing endpoints ────────────────────────────────────────────────────────

@app.get("/")
def root() -> Dict[str, str]:
    """Health-check / welcome endpoint."""
    return {"message": "Nifty 100 Financial Analytics API", "version": "1.0.0"}


@app.get("/companies")
def list_companies(
    sector: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> Dict[str, Any]:
    """List companies with optional sector filter and pagination."""
    with get_connection() as conn:
        if sector:
            rows = conn.execute(
                "SELECT * FROM companies WHERE sector_name = ? LIMIT ? OFFSET ?",
                [sector, limit, offset],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM companies LIMIT ? OFFSET ?",
                [limit, offset],
            ).fetchall()
        return {"count": len(rows), "data": [dict(r) for r in rows]}


@app.get("/ratios/{company_id}")
def get_ratios(company_id: int, year: Optional[int] = None) -> Dict[str, Any]:
    """Return financial ratios for a company, optionally filtered by year."""
    with get_connection() as conn:
        comp = _fetch_company(conn, company_id)
        if year:
            rows = conn.execute(
                "SELECT * FROM financial_ratios WHERE company_id = ? AND year = ?",
                [company_id, year],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year DESC",
                [company_id],
            ).fetchall()
        return {
            "company_id": company_id,
            "ticker": comp["ticker"],
            "name": comp["company_name"],
            "ratios": [dict(r) for r in rows],
        }


@app.get("/screener/{preset}")
def run_screener(preset: str) -> Dict[str, Any]:
    """Run a predefined screener preset."""
    from src.screener.engine import ScreenerEngine
    engine = ScreenerEngine(db_path=DB_PATH)
    result = engine.screen(preset)
    return {"preset": preset, "count": len(result), "data": result.to_dict(orient="records")}


@app.get("/dashboard")
def dashboard() -> Dict[str, Any]:
    """High-level dashboard summary of the database."""
    with get_connection() as conn:
        tables = [
            "companies", "profitandloss", "balancesheet", "cashflow",
            "stock_prices", "financial_ratios",
        ]
        totals = {}
        for t in tables:
            totals[t] = conn.execute(f"SELECT COUNT(*) AS cnt FROM {t}").fetchone()["cnt"]

        sectors = conn.execute(
            "SELECT sector_name, COUNT(*) AS cnt FROM companies "
            "GROUP BY sector_name ORDER BY cnt DESC"
        ).fetchall()

        yr = conn.execute(
            "SELECT MIN(year) AS mn, MAX(year) AS mx FROM profitandloss"
        ).fetchone()

        top = conn.execute(
            "SELECT ticker, company_name, market_cap FROM companies "
            "ORDER BY market_cap DESC LIMIT 5"
        ).fetchall()

        return {
            "table_counts": totals,
            "sectors": [dict(r) for r in sectors],
            "year_range": {
                "min": yr["mn"],
                "max": yr["mx"],
            },
            "top_by_market_cap": [dict(r) for r in top],
        }


# ── New endpoints ─────────────────────────────────────────────────────────────

# 6. Full company profile
@app.get("/company/{company_id}")
def get_company_profile(company_id: int) -> Dict[str, Any]:
    """Return full company profile: info, latest ratios, pros/cons."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        latest_ratio = conn.execute(
            "SELECT * FROM financial_ratios WHERE company_id = ? "
            "ORDER BY year DESC LIMIT 1",
            [company_id],
        ).fetchone()

        pros_row = conn.execute(
            "SELECT * FROM prosandcons WHERE company_id = ? LIMIT 1",
            [company_id],
        ).fetchone()

        return {
            "company": company,
            "latest_ratios": dict(latest_ratio) if latest_ratio else None,
            "pros_and_cons": {
                "pros": pros_row["pros"] if pros_row else None,
                "cons": pros_row["cons"] if pros_row else None,
            },
        }


# 7. All financial statements for a company
@app.get("/company/{company_id}/financials")
def get_company_financials(company_id: int) -> Dict[str, Any]:
    """Return all P&L, balance-sheet, and cash-flow data across years."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        pnl = conn.execute(
            "SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year DESC",
            [company_id],
        ).fetchall()

        bs = conn.execute(
            "SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year DESC",
            [company_id],
        ).fetchall()

        cf = conn.execute(
            "SELECT * FROM cashflow WHERE company_id = ? ORDER BY year DESC",
            [company_id],
        ).fetchall()

        return {
            "company_id": company_id,
            "ticker": company["ticker"],
            "name": company["company_name"],
            "profit_and_loss": [dict(r) for r in pnl],
            "balance_sheet": [dict(r) for r in bs],
            "cash_flow": [dict(r) for r in cf],
        }


# 8. Peer comparison with percentile ranks
@app.get("/peer/{company_id}")
def get_peer_comparison(company_id: int) -> Dict[str, Any]:
    """Return peer-group percentile ranks for a company across all metrics."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        rows = conn.execute(
            "SELECT metric_name, percentile_rank, peer_group, year "
            "FROM peer_percentiles WHERE company_id = ? "
            "ORDER BY metric_name, year DESC",
            [company_id],
        ).fetchall()

        percentiles: Dict[str, List[Dict]] = {}
        for r in rows:
            metric = r["metric_name"]
            entry = {
                "percentile_rank": r["percentile_rank"],
                "peer_group": r["peer_group"],
                "year": r["year"],
            }
            percentiles.setdefault(metric, []).append(entry)

        return {
            "company_id": company_id,
            "ticker": company["ticker"],
            "name": company["company_name"],
            "sector": company["sector_name"],
            "peer_percentiles": percentiles,
        }


# 9. All companies ranked by a given metric
@app.get("/peers/{metric}")
def get_peers_by_metric(
    metric: str,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> Dict[str, Any]:
    """Return all companies ranked by percentile_rank for a given metric."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT c.company_id, c.ticker, c.company_name, c.sector_name, "
            "pp.percentile_rank, pp.peer_group, pp.year "
            "FROM peer_percentiles pp "
            "JOIN companies c ON pp.company_id = c.company_id "
            "WHERE pp.metric_name = ? "
            "ORDER BY pp.percentile_rank DESC "
            "LIMIT ? OFFSET ?",
            [metric, limit, offset],
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM peer_percentiles WHERE metric_name = ?",
            [metric],
        ).fetchone()["cnt"]

        return {
            "metric": metric,
            "total": total,
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# 10. List all sectors with company counts and average metrics
@app.get("/sectors")
def list_sectors() -> Dict[str, Any]:
    """List all sectors with company counts and average latest-year ratios."""
    with get_connection() as conn:
        sectors = conn.execute(
            "SELECT sector_name, COUNT(*) AS company_count "
            "FROM companies GROUP BY sector_name ORDER BY company_count DESC"
        ).fetchall()

        # Average metrics per sector (latest financial_ratios year per company)
        avg_metrics = conn.execute(
            "SELECT c.sector_name, "
            "AVG(fr.roe) AS avg_roe, "
            "AVG(fr.roce) AS avg_roce, "
            "AVG(fr.debt_to_equity) AS avg_debt_to_equity, "
            "AVG(fr.net_profit_margin) AS avg_net_profit_margin, "
            "AVG(fr.pe_ratio) AS avg_pe_ratio, "
            "AVG(fr.pb_ratio) AS avg_pb_ratio "
            "FROM companies c "
            "JOIN financial_ratios fr ON c.company_id = fr.company_id "
            "WHERE fr.year = (SELECT MAX(year) FROM financial_ratios WHERE company_id = c.company_id) "
            "GROUP BY c.sector_name"
        ).fetchall()

        avg_map = {r["sector_name"]: dict(r) for r in avg_metrics}

        result = []
        for s in sectors:
            entry = dict(s)
            metrics = avg_map.get(s["sector_name"], {})
            entry["avg_roe"] = metrics.get("avg_roe")
            entry["avg_roce"] = metrics.get("avg_roce")
            entry["avg_debt_to_equity"] = metrics.get("avg_debt_to_equity")
            entry["avg_net_profit_margin"] = metrics.get("avg_net_profit_margin")
            entry["avg_pe_ratio"] = metrics.get("avg_pe_ratio")
            entry["avg_pb_ratio"] = metrics.get("avg_pb_ratio")
            result.append(entry)

        return {"count": len(result), "sectors": result}


# 11. Companies in a specific sector with their metrics
@app.get("/sector/{sector_name}")
def get_sector_companies(
    sector_name: str,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> Dict[str, Any]:
    """Return companies in a given sector with their latest financial ratios."""
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM companies WHERE sector_name = ?",
            [sector_name],
        ).fetchone()["cnt"]

        if total == 0:
            raise HTTPException(status_code=404, detail=f"Sector '{sector_name}' not found")

        rows = conn.execute(
            "SELECT c.company_id, c.ticker, c.company_name, c.market_cap, "
            "c.website, c.isin, "
            "fr.roe, fr.roce, fr.debt_to_equity, fr.net_profit_margin, "
            "fr.pe_ratio, fr.pb_ratio, fr.dividend_yield, fr.year AS ratio_year "
            "FROM companies c "
            "LEFT JOIN financial_ratios fr ON c.company_id = fr.company_id "
            "AND fr.year = (SELECT MAX(year) FROM financial_ratios WHERE company_id = c.company_id) "
            "WHERE c.sector_name = ? "
            "ORDER BY c.market_cap DESC "
            "LIMIT ? OFFSET ?",
            [sector_name, limit, offset],
        ).fetchall()

        return {
            "sector": sector_name,
            "total": total,
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# 12. CAGR data (3y, 5y, 10y) from analysis table
@app.get("/cagr/{company_id}")
def get_cagr(company_id: int) -> Dict[str, Any]:
    """Return CAGR (3y, 5y, 10y) for revenue, PAT, EPS from analysis table."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        rows = conn.execute(
            "SELECT analysis_type, metric_name, metric_value, year "
            "FROM analysis WHERE company_id = ? AND analysis_type LIKE 'cagr%' "
            "ORDER BY analysis_type, metric_name",
            [company_id],
        ).fetchall()

        if not rows:
            return {
                "company_id": company_id,
                "ticker": company["ticker"],
                "name": company["company_name"],
                "cagr": {},
                "message": "No CAGR data available",
            }

        # Group by metric_name → {period: value}
        cagr_data: Dict[str, Dict[str, float]] = {}
        for r in rows:
            at = r["analysis_type"]          # e.g. "cagr_3y", "cagr_5y"
            mn = r["metric_name"]            # e.g. "revenue", "pat", "eps"
            mv = r["metric_value"]
            period = at.replace("cagr_", "")  # "3y", "5y", "10y"
            cagr_data.setdefault(mn, {})[period] = mv

        return {
            "company_id": company_id,
            "ticker": company["ticker"],
            "name": company["company_name"],
            "cagr": cagr_data,
        }


# 13. Latest stock price data (last 30 trading days)
@app.get("/stock/{company_id}")
def get_stock_latest(company_id: int) -> Dict[str, Any]:
    """Return the latest 30 trading days of stock price data for a company."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        rows = conn.execute(
            "SELECT trade_date, open, high, low, close, volume "
            "FROM stock_prices WHERE company_id = ? "
            "ORDER BY trade_date DESC LIMIT 30",
            [company_id],
        ).fetchall()

        return {
            "company_id": company_id,
            "ticker": company["ticker"],
            "name": company["company_name"],
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# 14. Full stock price history with pagination
@app.get("/stock/{company_id}/history")
def get_stock_history(
    company_id: int,
    limit: int = Query(500, le=5000),
    offset: int = 0,
) -> Dict[str, Any]:
    """Return full stock price history for a company with pagination."""
    with get_connection() as conn:
        company = _fetch_company(conn, company_id)

        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM stock_prices WHERE company_id = ?",
            [company_id],
        ).fetchone()["cnt"]

        rows = conn.execute(
            "SELECT trade_date, open, high, low, close, volume "
            "FROM stock_prices WHERE company_id = ? "
            "ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            [company_id, limit, offset],
        ).fetchall()

        return {
            "company_id": company_id,
            "ticker": company["ticker"],
            "name": company["company_name"],
            "total": total,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "data": [dict(r) for r in rows],
        }


# 15. Search companies by name or ticker
@app.get("/search")
def search_companies(
    q: str = Query(..., min_length=1, description="Search term for company name or ticker"),
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> Dict[str, Any]:
    """Search companies by ticker or company name (case-insensitive LIKE)."""
    with get_connection() as conn:
        pattern = f"%{q}%"
        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM companies "
            "WHERE ticker LIKE ? OR company_name LIKE ?",
            [pattern, pattern],
        ).fetchone()["cnt"]

        rows = conn.execute(
            "SELECT company_id, ticker, company_name, sector_name, market_cap, "
            "listing_status, website, isin "
            "FROM companies "
            "WHERE ticker LIKE ? OR company_name LIKE ? "
            "ORDER BY market_cap DESC "
            "LIMIT ? OFFSET ?",
            [pattern, pattern, limit, offset],
        ).fetchall()

        return {
            "query": q,
            "total": total,
            "count": len(rows),
            "data": [dict(r) for r in rows],
        }


# 16. Database health check
@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Return database health: row counts, foreign-key orphan counts, DB status."""
    health: Dict[str, Any] = {
        "database": str(Path(DB_PATH).resolve()),
        "db_exists": os.path.isfile(DB_PATH),
        "status": "ok",
        "tables": {},
        "foreign_key_issues": {},
    }

    if not health["db_exists"]:
        health["status"] = "error"
        return health

    with get_connection() as conn:
        # Row counts for every user table
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

        for tbl in tables:
            name = tbl["name"]
            cnt = conn.execute(f"SELECT COUNT(*) AS cnt FROM [{name}]").fetchone()["cnt"]
            health["tables"][name] = cnt

        # Foreign-key orphan checks (child rows referencing non-existent companies)
        fk_checks = [
            ("profitandloss", "company_id"),
            ("balancesheet", "company_id"),
            ("cashflow", "company_id"),
            ("financial_ratios", "company_id"),
            ("peer_percentiles", "company_id"),
            ("stock_prices", "company_id"),
            ("analysis", "company_id"),
            ("market_cap_annual", "company_id"),
            ("prosandcons", "company_id"),
            ("documents", "company_id"),
        ]

        for table_name, fk_col in fk_checks:
            try:
                orphan_cnt = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM [{table_name}] c "
                    f"LEFT JOIN companies co ON c.{fk_col} = co.company_id "
                    "WHERE co.company_id IS NULL"
                ).fetchone()["cnt"]
                if orphan_cnt > 0:
                    health["foreign_key_issues"][table_name] = orphan_cnt
            except sqlite3.OperationalError:
                pass  # table might not exist yet

        if health["foreign_key_issues"]:
            health["status"] = "warning"

        return health


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
