from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
from pathlib import Path

app = FastAPI(title="Nifty 100 Financial Analytics API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = "db/nifty100.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
def root():
    return {"message": "Nifty 100 Financial Analytics API", "version": "1.0.0"}

@app.get("/companies")
def list_companies(sector: str = None, limit: int = Query(100, le=500), offset: int = 0):
    conn = get_db()
    try:
        if sector:
            df = pd.read_sql("SELECT * FROM companies WHERE sector_name = ? LIMIT ? OFFSET ?", conn, params=[sector, limit, offset])
        else:
            df = pd.read_sql("SELECT * FROM companies LIMIT ? OFFSET ?", conn, params=[limit, offset])
        return {"count": len(df), "data": df.to_dict(orient="records")}
    finally:
        conn.close()

@app.get("/ratios/{company_id}")
def get_ratios(company_id: int, year: int = None):
    conn = get_db()
    try:
        ticker = conn.execute("SELECT ticker, company_name FROM companies WHERE company_id = ?", [company_id]).fetchone()
        if not ticker:
            raise HTTPException(404, "Company not found")
        if year:
            df = pd.read_sql("SELECT * FROM financial_ratios WHERE company_id = ? AND year = ?", conn, params=[company_id, year])
        else:
            df = pd.read_sql("SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year DESC", conn, params=[company_id])
        ratios = df.to_dict(orient="records")
        return {"company_id": company_id, "ticker": ticker["ticker"], "name": ticker["company_name"], "ratios": ratios}
    finally:
        conn.close()

@app.get("/screener/{preset}")
def run_screener(preset: str):
    from src.screener.engine import ScreenerEngine
    engine = ScreenerEngine(db_path=DB_PATH)
    result = engine.screen(preset)
    return {"preset": preset, "count": len(result), "data": result.to_dict(orient="records")}

@app.get("/dashboard")
def dashboard():
    conn = get_db()
    try:
        totals = {}
        for table in ["companies", "profitandloss", "balancesheet", "cashflow", "stock_prices", "financial_ratios"]:
            totals[table] = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()["cnt"]

        sectors = pd.read_sql("SELECT sector_name, COUNT(*) as cnt FROM companies GROUP BY sector_name ORDER BY cnt DESC", conn)
        years = pd.read_sql("SELECT MIN(year) as min_year, MAX(year) as max_year FROM profitandloss", conn).iloc[0]
        top_mcap = pd.read_sql("SELECT ticker, company_name, market_cap FROM companies ORDER BY market_cap DESC LIMIT 5", conn)

        return {
            "table_counts": totals,
            "sectors": sectors.to_dict(orient="records"),
            "year_range": {"min": int(years["min_year"]) if years["min_year"] else None, "max": int(years["max_year"]) if years["max_year"] else None},
            "top_by_market_cap": top_mcap.to_dict(orient="records")
        }
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
