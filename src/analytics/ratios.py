"""Financial Ratio Engine — Sprint 2.

Computes profitability, leverage, efficiency, cash-flow and growth (CAGR)
KPIs for every company-year and populates the `financial_ratios` table.

Formula conventions (per spec):
  * NPM  = net_profit / sales * 100               (None if sales = 0)
  * OPM  = operating_profit / sales * 100         (None if sales = 0)
  * ROE  = net_profit / (equity + reserves) * 100 (None if <= 0)
  * ROCE = EBIT / (equity + reserves + borrowings) * 100
  * ROA  = net_profit / total_assets * 100        (None if assets = 0)
  * D/E  = borrowings / (equity + reserves)       (0 if borrowings = 0)
  * ICR  = (operating_profit + other_income) / interest (None if interest = 0)
  * Net Debt = borrowings - investments
  * Asset Turnover = sales / total_assets
"""

import logging
import os
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ratios")

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (ValueError, TypeError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── Standalone ratio functions (unit-testable) ────────────────────────

def net_profit_margin(net_profit, sales):
    if not sales or sales == 0 or net_profit is None:
        return None
    return net_profit / sales * 100


def operating_profit_margin(operating_profit, sales):
    if not sales or sales == 0 or operating_profit is None:
        return None
    return operating_profit / sales * 100


def return_on_equity(net_profit, equity_capital, reserves=0.0):
    equity = (equity_capital or 0) + (reserves or 0)
    if equity <= 0 or net_profit is None:
        return None
    return net_profit / equity * 100


def return_on_capital_employed(ebit, equity_capital, reserves, borrowings):
    capital = (equity_capital or 0) + (reserves or 0) + (borrowings or 0)
    if capital <= 0 or ebit is None:
        return None
    return ebit / capital * 100


def return_on_assets(net_profit, total_assets):
    if not total_assets or total_assets == 0 or net_profit is None:
        return None
    return net_profit / total_assets * 100


def debt_to_equity(borrowings, equity_capital, reserves=0.0):
    equity = (equity_capital or 0) + (reserves or 0)
    if equity <= 0:
        return None
    if not borrowings or borrowings == 0:
        return 0.0
    return borrowings / equity


def interest_coverage_ratio(operating_profit, other_income, interest):
    if not interest or interest == 0:
        return None
    ebit = (operating_profit or 0) + (other_income or 0)
    return ebit / interest


def net_debt(borrowings, investments):
    return (borrowings or 0) - (investments or 0)


def asset_turnover(sales, total_assets):
    if not sales or not total_assets or total_assets == 0:
        return None
    return sales / total_assets


def book_value_per_share(equity_capital, reserves, face_value):
    if not equity_capital or equity_capital == 0 or not face_value:
        return None
    return (equity_capital + (reserves or 0)) * face_value / equity_capital


def opm_cross_check(operating_profit_margin_pct, opm_percentage):
    """Cross-check computed OPM against the source opm_percentage field.

    Returns True when the two diverge by more than 1 percentage point.
    """
    if operating_profit_margin_pct is None or opm_percentage is None:
        return False
    source = opm_percentage / 100.0 if abs(opm_percentage) > 1 else opm_percentage
    return abs(operating_profit_margin_pct / 100.0 - source) >= 0.01


# ── RatioEngine ───────────────────────────────────────────────────────

class RatioEngine:
    """Computes all ratios and populates the financial_ratios table."""

    def __init__(self, db_path: str = "db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")

    def _is_financial(self, sector) -> bool:
        return bool(sector) and "financial" in str(sector).lower()

    def compute_all(self, company_id=None) -> pd.DataFrame:
        """Compute base profitability/leverage/efficiency ratios per company-year."""
        query = """
            SELECT p.company_id, p.year,
                   p.sales, p.operating_profit, p.other_income, p.interest,
                   p.net_profit, p.eps, p.dividend_payout, p.depreciation,
                   b.equity_capital, b.reserves, b.borrowings, b.investments,
                   b.total_assets, b.total_liabilities,
                   c.broad_sector, c.face_value, c.ticker
            FROM profitandloss p
            LEFT JOIN balancesheet b ON p.company_id = b.company_id AND p.year = b.year
            LEFT JOIN companies c ON p.company_id = c.company_id
        """
        params = {}
        if company_id is not None:
            query += " WHERE p.company_id = :cid"
            params["cid"] = int(company_id)

        df = pd.read_sql_query(text(query), self.engine, params=params or None)
        if df.empty:
            return pd.DataFrame()

        rows = []
        for _, r in df.iterrows():
            cid = int(r["company_id"])
            yr = int(r["year"])
            sector = r["broad_sector"]
            is_fin = self._is_financial(sector)

            sales = _num(r["sales"])
            op = _num(r["operating_profit"])
            oi = _num(r["other_income"])
            interest = _num(r["interest"])
            np_ = _num(r["net_profit"])
            equity_cap = _num(r["equity_capital"])
            reserves = _num(r["reserves"])
            borrowings = _num(r["borrowings"])
            investments = _num(r["investments"])
            total_assets = _num(r["total_assets"])
            face_value = _num(r["face_value"])

            ebit = (op or 0) + (oi or 0)
            roe = return_on_equity(np_, equity_cap, reserves)
            de = debt_to_equity(borrowings, equity_cap, reserves)
            icr = interest_coverage_ratio(op, oi, interest)

            # Flags
            icr_label = None
            if interest is not None and interest == 0 and (op or 0) > 0:
                icr_label = "Debt Free"
            icr_warning = (icr is not None and icr < 1.5)
            high_leverage = (de is not None and de > 5 and not is_fin)

            rows.append({
                "company_id": cid, "year": yr,
                "net_profit_margin_pct": net_profit_margin(np_, sales),
                "operating_profit_margin_pct": operating_profit_margin(op, sales),
                "return_on_equity_pct": roe,
                "return_on_capital_employed_pct": return_on_capital_employed(ebit, equity_cap, reserves, borrowings),
                "return_on_assets_pct": return_on_assets(np_, total_assets),
                "debt_to_equity": de,
                "interest_coverage": icr,
                "icr_label": icr_label,
                "high_leverage_flag": bool(high_leverage),
                "icr_warning_flag": bool(icr_warning),
                "net_debt_cr": net_debt(borrowings, investments),
                "asset_turnover": asset_turnover(sales, total_assets),
                "earnings_per_share": _num(r["eps"]),
                "book_value_per_share": book_value_per_share(equity_cap, reserves, face_value),
                "dividend_payout_ratio_pct": _num(r["dividend_payout"]),
                "total_debt_cr": borrowings,
            })
        return pd.DataFrame(rows)

    def _merge_cashflow(self, base: pd.DataFrame) -> pd.DataFrame:
        from src.analytics.cashflow_kpis import CashFlowAnalyzer
        cf = CashFlowAnalyzer(self.db_path).compute()
        if not base.empty:
            cfo = pd.read_sql_query(
                text("SELECT company_id, year, operating_activity FROM cashflow"), self.engine)
            base = base.merge(cfo.rename(columns={"operating_activity": "cash_from_operations_cr"}),
                              on=["company_id", "year"], how="left")
        if cf.empty or base.empty:
            return base
        base = base.merge(
            cf[["company_id", "year", "free_cash_flow_cr", "cfo_quality_score",
                "cfo_quality_label", "capex_intensity_pct", "capex_intensity_label",
                "fcf_conversion_pct", "capital_allocation_pattern"]],
            on=["company_id", "year"], how="left")
        return base

    def _merge_cagr(self, df: pd.DataFrame) -> pd.DataFrame:
        from src.analytics.cagr import CAGRCalculator
        calc = CAGRCalculator(self.db_path)
        cagr_df = calc.compute_all()
        if cagr_df.empty or df.empty:
            return df

        latest = df.groupby("company_id")["year"].transform("max") == df["year"]
        for metric in ["revenue", "pat", "eps"]:
            for w in [3, 5, 10]:
                col = f"{metric}_cagr_{w}yr"
                sub = cagr_df[(cagr_df["metric"] == metric) & (cagr_df["window"] == w)]
                m = sub.set_index("company_id")[["value", "flag"]].rename(
                    columns={"value": col, "flag": col + "_flag"})
                df = df.merge(m, left_on="company_id", right_index=True, how="left")
                df.loc[~latest, col] = None
                df.loc[~latest, col + "_flag"] = None
        return df

    def compute_ratios(self, company_id=None):
        """Backward-compatible wrapper."""
        df = self.compute_all(company_id)
        df = self._merge_cashflow(df)
        return df

    def run(self) -> dict:
        logger.info("Computing financial ratios...")
        base = self.compute_all()
        base = self._merge_cashflow(base)
        base = self._merge_cagr(base)

        base["composite_quality_score"] = None  # populated in Sprint 3
        self._store(base)

        from src.analytics.exports import export_capital_allocation, export_ratio_edge_cases
        export_capital_allocation(self.db_path)
        export_ratio_edge_cases(self.db_path)

        total = len(base)
        companies = base["company_id"].nunique() if not base.empty else 0
        logger.info(f"Ratio engine done: {total} rows across {companies} companies")
        return {"total_rows": total, "companies": companies}

    def _store(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        cols = [
            "company_id", "year",
            "net_profit_margin_pct", "operating_profit_margin_pct",
            "return_on_equity_pct", "return_on_capital_employed_pct", "return_on_assets_pct",
            "debt_to_equity", "interest_coverage", "icr_label",
            "high_leverage_flag", "icr_warning_flag", "net_debt_cr", "asset_turnover",
            "free_cash_flow_cr", "capex_cr", "fcf_conversion_pct", "capex_intensity_pct",
            "cfo_quality_score", "cfo_quality_label", "capital_allocation_pattern",
            "earnings_per_share", "book_value_per_share", "dividend_payout_ratio_pct",
            "total_debt_cr", "cash_from_operations_cr",
            "revenue_cagr_3yr", "revenue_cagr_5yr", "revenue_cagr_10yr",
            "pat_cagr_3yr", "pat_cagr_5yr", "pat_cagr_10yr",
            "eps_cagr_3yr", "eps_cagr_5yr", "eps_cagr_10yr",
            "revenue_cagr_5yr_flag", "pat_cagr_5yr_flag", "eps_cagr_5yr_flag",
            "composite_quality_score",
        ]
        store = df[[c for c in cols if c in df.columns]].copy()
        # capex_cr = magnitude of negative investing activity (net capital expenditure)
        cf = pd.read_sql_query(
            text("SELECT company_id, year, investing_activity FROM cashflow"), self.engine)
        store = store.merge(cf, on=["company_id", "year"], how="left")
        store["capex_cr"] = store["investing_activity"].apply(
            lambda x: abs(x) if pd.notna(x) and x < 0 else 0.0)
        store = store.drop(columns=["investing_activity"])

        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM financial_ratios"))
        store.to_sql("financial_ratios", self.engine, if_exists="append", index=False)
        logger.info(f"Stored {len(store)} rows in financial_ratios")


if __name__ == "__main__":
    result = RatioEngine().run()
    print(f"Done: {result}")
