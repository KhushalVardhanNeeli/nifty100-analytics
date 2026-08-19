"""Shared cached data loader for the Streamlit dashboard (Sprint 4).

Every query is wrapped in @st.cache_data(ttl=600). All functions return
pandas DataFrames keyed on the spec-aligned schema column names.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "db" / "nifty100.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent.parent


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=600)
def _query(sql, params=None) -> pd.DataFrame:
    conn = _conn()
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


# ── Core lookups ──────────────────────────────────────────────────────


@st.cache_data(ttl=600)
def get_companies() -> pd.DataFrame:
    return _query(
        "SELECT company_id, ticker, company_name, broad_sector, sub_sector, "
        "about_company, website, market_cap_crore, roe_percentage, roce_percentage "
        "FROM companies ORDER BY ticker"
    )


@st.cache_data(ttl=600)
def get_sectors() -> list:
    df = _query(
        "SELECT DISTINCT broad_sector FROM companies "
        "WHERE broad_sector IS NOT NULL ORDER BY broad_sector"
    )
    return df["broad_sector"].tolist() if not df.empty else []


@st.cache_data(ttl=600)
def get_latest_year() -> int:
    df = _query("SELECT MAX(year) AS y FROM financial_ratios")
    return int(df.iloc[0]["y"]) if not df.empty else 2024


@st.cache_data(ttl=600)
def get_year_range() -> tuple:
    df = _query("SELECT MIN(year) AS mn, MAX(year) AS mx FROM financial_ratios")
    if df.empty:
        return 2012, 2024
    return int(df.iloc[0]["mn"]), int(df.iloc[0]["mx"])


@st.cache_data(ttl=600)
def resolve_ticker(ticker: str):
    t = str(ticker or "").strip().upper()
    if not t:
        return None
    df = _query(
        "SELECT company_id, ticker, company_name FROM companies WHERE upper(ticker) = ?",
        params=[t],
    )
    return int(df.iloc[0]["company_id"]) if not df.empty else None


def get_company(ticker: str) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    return _query("SELECT * FROM companies WHERE company_id = ?", params=[cid])


# ── Financial statements ──────────────────────────────────────────────


def get_ratios(ticker: str, year: int | None = None) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    if year is None:
        return _query(
            "SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year",
            params=[cid],
        )
    return _query(
        "SELECT * FROM financial_ratios WHERE company_id = ? AND year = ? ORDER BY year",
        params=[cid, int(year)],
    )


def get_pl(ticker: str) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    return _query("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", params=[cid])


def get_bs(ticker: str) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    return _query("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", params=[cid])


def get_cf(ticker: str) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    return _query("SELECT * FROM cashflow WHERE company_id = ? ORDER BY year", params=[cid])


def get_valuation(ticker: str) -> pd.DataFrame:
    cid = resolve_ticker(ticker)
    if cid is None:
        return pd.DataFrame()
    return _query("SELECT * FROM market_cap WHERE company_id = ? ORDER BY year", params=[cid])


# ── Supporting data ───────────────────────────────────────────────────


@st.cache_data(ttl=600)
def get_peer_groups() -> list:
    df = _query("SELECT DISTINCT peer_group_name FROM peer_groups ORDER BY peer_group_name")
    return df["peer_group_name"].tolist() if not df.empty else []


@st.cache_data(ttl=600)
def get_peers(group_name: str) -> pd.DataFrame:
    return _query(
        """SELECT pg.company_id, c.ticker, c.company_name, pg.is_benchmark
           FROM peer_groups pg JOIN companies c ON c.company_id = pg.company_id
           WHERE pg.peer_group_name = ? ORDER BY c.ticker""",
        params=[group_name],
    )


@st.cache_data(ttl=600)
def get_peer_percentiles(company_id: int) -> pd.DataFrame:
    return _query(
        "SELECT metric, value, percentile_rank, peer_group, year FROM peer_percentiles "
        "WHERE company_id = ? ORDER BY metric",
        params=[int(company_id)],
    )


@st.cache_data(ttl=600)
def get_proscons(company_id: int) -> pd.DataFrame:
    return _query(
        "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
        params=[int(company_id)],
    )


@st.cache_data(ttl=600)
def get_documents(company_id: int) -> pd.DataFrame:
    return _query(
        "SELECT year, annual_report FROM documents WHERE company_id = ? ORDER BY year DESC",
        params=[int(company_id)],
    )


@st.cache_data(ttl=600)
def get_market_cap_for_year(year: int) -> pd.DataFrame:
    return _query(
        "SELECT mc.company_id, c.ticker, c.company_name, mc.market_cap_crore, "
        "mc.pe_ratio, mc.pb_ratio, mc.ev_ebitda, mc.dividend_yield_pct "
        "FROM market_cap mc JOIN companies c ON c.company_id = mc.company_id "
        "WHERE mc.year = ?",
        params=[int(year)],
    )


@st.cache_data(ttl=600)
def get_composite_scores() -> pd.DataFrame:
    """Composite quality score per company (from the screener engine)."""
    from src.screener.engine import ScreenerEngine

    eng = ScreenerEngine(db_path=str(DB_PATH))
    df = eng.load_data()
    df = eng.composite_score(df)
    return df[["company_id", "ticker", "composite_score"]].copy()
