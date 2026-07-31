"""Financial Ratio Engine — Sprint 2. Computes 20+ KPIs for all companies across all years.

Works with the actual DB schema loaded by the ETL pipeline.
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


def nvl(val, default: float = 0.0) -> float:
    """Return default if val is None or NaN."""
    if val is None:
        return default
    try:
        if np.isnan(float(val)):
            return default
    except (ValueError, TypeError):
        return default
    return float(val)


# ── Standalone ratio functions (for unit tests & backward compatibility) ──

def net_profit_margin(net_profit: float, sales: float) -> Optional[float]:
    if not sales or sales == 0:
        return None
    return (net_profit / sales) * 100


def operating_profit_margin(operating_profit: float, sales: float) -> Optional[float]:
    if not sales or sales == 0:
        return None
    return (operating_profit / sales) * 100


def return_on_equity(net_profit: float, equity_capital: float, reserves: float = 0.0) -> Optional[float]:
    equity = equity_capital + (reserves or 0)
    if equity <= 0:
        return None
    return (net_profit / equity) * 100


def return_on_capital_employed(ebit: float, equity_capital: float, reserves: float, borrowings: float) -> Optional[float]:
    """ROCE — return on capital employed. Backward-compatible signature."""
    capital = equity_capital + reserves + borrowings
    if capital <= 0:
        return None
    return (ebit / capital) * 100


def return_on_assets(net_profit: float, total_assets: float) -> Optional[float]:
    if not total_assets or total_assets == 0:
        return None
    return (net_profit / total_assets) * 100


def debt_to_equity(borrowings: float, equity_capital: float, reserves: float = 0.0) -> Optional[float]:
    equity = equity_capital + (reserves or 0)
    if equity <= 0:
        return None
    if not borrowings or borrowings == 0:
        return 0.0
    return borrowings / equity


def interest_coverage_ratio(op_profit: float, other_income_or_interest: float, interest: float = None) -> Optional[float]:
    # Support both: (op_profit, other_income, interest) and (op_profit, interest)
    if interest is not None:
        # 3-arg call: (op_profit, other_income, interest)
        if interest == 0:
            return None  # Debt-free
        ebit = (op_profit or 0) + (other_income_or_interest or 0)
        return ebit / interest
    else:
        # 2-arg call: (op_profit, interest) where other_income_or_interest is interest
        if not other_income_or_interest or other_income_or_interest == 0:
            return None  # Debt-free
        return op_profit / other_income_or_interest


def compute_cagr(start_value: float, end_value: float, n: int):
    """Standalone CAGR. Returns (value, flag)."""
    if n <= 0:
        return None, None
    if start_value == 0:
        return None, "ZERO_BASE"
    if start_value > 0 and end_value > 0:
        cagr = ((end_value / start_value) ** (1 / n) - 1) * 100
        return round(cagr, 2), None
    elif start_value > 0 and end_value < 0:
        return None, "DECLINE_TO_LOSS"
    elif start_value < 0 and end_value > 0:
        return None, "TURNAROUND"
    else:
        return None, "BOTH_NEGATIVE"


# ── RatioEngine class ────────────────────────────────────────────────────

class RatioEngine:
    """Computes all financial ratios from P&L, BS, CF, and stores results."""

    def __init__(self, db_path: str = "db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.financial_warnings: list[str] = []
        self.icr_warnings: list[str] = []
        self._companies: pd.DataFrame = pd.DataFrame()

    def _is_financial(self, sector_name: Optional[str]) -> bool:
        if not sector_name:
            return False
        s = str(sector_name).lower()
        return any(kw in s for kw in ["financial", "bfsi", "bank"])

    def compute_ratios(self, company_id=None):
        """Backward-compatible wrapper for per-company computation."""
        return self.compute_all(company_id)

    def compute_all(self, company_id=None) -> pd.DataFrame:
        """Compute ratios for all company-year combinations."""

        query = """
            SELECT p.company_id, p.year,
                p.sales, p.operating_profit, p.operating_profit_margin,
                p.net_profit, p.eps, p.dividend_payout_pct, p.tax_rate,
                p.depreciation, p.interest_expense, p.other_income,
                p.total_revenue, p.cogs,
                b.total_assets, b.total_liabilities, b.shareholders_equity,
                b.total_debt, b.current_assets, b.current_liabilities,
                b.cash_and_equivalents, b.inventory, b.investments,
                b.fixed_assets,
                c.sector_name, c.market_cap, c.ticker
            FROM profitandloss p
            LEFT JOIN balancesheet b ON p.company_id = b.company_id AND p.year = b.year
            LEFT JOIN companies c ON p.company_id = c.company_id
        """
        params = {}
        if company_id is not None:
            query += " WHERE p.company_id = :cid"
            params["cid"] = int(company_id)

        df = pd.read_sql_query(text(query), self.engine, params=params if params else None)
        if df.empty:
            logger.warning("No data found for ratio computation")
            return pd.DataFrame()

        ratios_list = []
        for _, row in df.iterrows():
            cid = int(row["company_id"])
            yr = int(row["year"])
            sector = row.get("sector_name")
            is_fin = self._is_financial(sector)

            sales = nvl(row.get("sales"))
            net_profit = row.get("net_profit")
            op_profit = nvl(row.get("operating_profit"))
            total_assets = nvl(row.get("total_assets"))
            equity = nvl(row.get("shareholders_equity"))
            total_debt = nvl(row.get("total_debt"))
            cash = nvl(row.get("cash_and_equivalents"))
            cur_assets = nvl(row.get("current_assets"))
            cur_liab = nvl(row.get("current_liabilities"))
            inventory = nvl(row.get("inventory"))
            depreciation = nvl(row.get("depreciation"))
            interest_expense = nvl(row.get("interest_expense"))
            tax_rate = row.get("tax_rate")  # already decimal
            cogs = nvl(row.get("cogs"))
            eps = row.get("eps")
            div_payout = row.get("dividend_payout_pct")  # already decimal
            mcap = row.get("market_cap")
            investments = nvl(row.get("investments"))
            other_income = nvl(row.get("other_income"))

            entry: dict = {"company_id": cid, "year": yr}

            # Profitability
            entry["net_profit_margin"] = (
                (net_profit / sales * 100)
                if sales and sales != 0 and net_profit is not None
                else None
            )
            entry["operating_profit_margin"] = (
                (op_profit / sales * 100)
                if sales and sales != 0 and op_profit is not None
                else None
            )
            gross_profit = sales - cogs if sales and cogs else None
            entry["gross_profit_margin"] = (
                (gross_profit / sales * 100)
                if gross_profit is not None and sales and sales != 0
                else None
            )

            # ROE
            entry["roe"] = (
                (net_profit / equity * 100)
                if equity > 0 and net_profit is not None
                else None
            )

            # ROCE = operating_profit / (total_assets - current_liabilities)
            denom_roce = total_assets - cur_liab if total_assets else 0
            entry["roce"] = (
                (op_profit / denom_roce * 100)
                if denom_roce > 0 and op_profit is not None
                else None
            )

            # ROA
            entry["roa"] = (
                (net_profit / total_assets * 100)
                if total_assets > 0 and net_profit is not None
                else None
            )

            # ROIC = operating_profit * (1 - tax_rate) / (total_debt + equity)
            invested_capital = total_debt + equity
            if invested_capital > 0 and op_profit is not None:
                tr = nvl(tax_rate, 0.25)
                entry["roic"] = (op_profit * (1 - tr)) / invested_capital * 100
            else:
                entry["roic"] = None

            # Debt-to-Equity
            if equity <= 0:
                entry["debt_to_equity"] = None
            elif total_debt == 0:
                entry["debt_to_equity"] = 0.0
            else:
                entry["debt_to_equity"] = total_debt / equity

            if is_fin and entry["debt_to_equity"] is not None and entry["debt_to_equity"] > 5:
                self.financial_warnings.append(
                    f"{cid}:{yr} | Financial sector D/E={entry['debt_to_equity']:.2f} > 5"
                )

            # Interest Coverage = (operating_profit + other_income) / interest
            ebit = op_profit + other_income
            if interest_expense == 0:
                entry["interest_coverage"] = None
                if op_profit > 0:
                    self.icr_warnings.append(f"{cid}:{yr} | Debt Free (interest_expense=0)")
            else:
                entry["interest_coverage"] = ebit / interest_expense
                if entry["interest_coverage"] < 1.5:
                    self.icr_warnings.append(
                        f"{cid}:{yr} | ICR={entry['interest_coverage']:.2f} < 1.5"
                    )

            # Net Debt
            entry["net_debt"] = total_debt - cash - investments

            # Net Debt to EBITDA
            ebitda = op_profit + depreciation
            entry["net_debt_to_ebitda"] = (
                entry["net_debt"] / ebitda if ebitda > 0 else None
            )

            # Asset Turnover
            entry["asset_turnover"] = (
                sales / total_assets if sales and total_assets > 0 else None
            )

            # Current Ratio
            entry["current_ratio"] = (
                cur_assets / cur_liab
                if cur_assets and cur_liab and cur_liab != 0
                else None
            )

            # Quick Ratio
            entry["quick_ratio"] = (
                (cur_assets - inventory) / cur_liab
                if cur_assets and inventory is not None and cur_liab and cur_liab != 0
                else None
            )

            # Inventory Turnover
            entry["inventory_turnover"] = None  # Need inventory data not available

            # Dividend Yield — from market_cap_annual or companies
            entry["dividend_yield"] = None
            if div_payout is not None and eps is not None and eps != 0:
                dps = div_payout * eps  # div_payout is decimal fraction
                # Try getting close price from stock_prices
                try:
                    sp_df = pd.read_sql_query(
                        text(
                            "SELECT close FROM stock_prices "
                            "WHERE company_id = :cid "
                            "AND CAST(substr(trade_date, 1, 4) AS INTEGER) = :yr "
                            "ORDER BY trade_date DESC LIMIT 1"
                        ),
                        self.engine,
                        params={"cid": cid, "yr": yr},
                    )
                    if not sp_df.empty:
                        cp = sp_df.iloc[0]["close"]
                        if cp and cp != 0:
                            entry["dividend_yield"] = dps / cp * 100
                except Exception:
                    pass

            # FCF Yield = FCF / Market Cap
            entry["fcf_yield"] = None
            try:
                cf_df = pd.read_sql_query(
                    text(
                        "SELECT fcf FROM cashflow WHERE company_id = :cid AND year = :yr"
                    ),
                    self.engine,
                    params={"cid": cid, "yr": yr},
                )
                if not cf_df.empty:
                    fcf_val = cf_df.iloc[0]["fcf"]
                    if fcf_val and mcap and mcap != 0:
                        entry["fcf_yield"] = fcf_val / mcap * 100
            except Exception:
                pass

            # EV / EBITDA (Enterprise Value not reliably available)
            entry["ev_to_ebitda"] = None

            # P/E Ratio
            entry["pe_ratio"] = None
            if eps and eps != 0:
                try:
                    sp_df = pd.read_sql_query(
                        text(
                            "SELECT close FROM stock_prices "
                            "WHERE company_id = :cid "
                            "AND CAST(substr(trade_date, 1, 4) AS INTEGER) = :yr "
                            "ORDER BY trade_date DESC LIMIT 1"
                        ),
                        self.engine,
                        params={"cid": cid, "yr": yr},
                    )
                    if not sp_df.empty:
                        cp = sp_df.iloc[0]["close"]
                        if cp and cp != 0:
                            entry["pe_ratio"] = cp / eps
                except Exception:
                    pass

            # P/B Ratio
            entry["pb_ratio"] = (
                mcap / equity
                if mcap and equity > 0
                else None
            )

            # CFO Quality — from cashflow_analyzer
            entry["cfo_quality"] = None
            entry["capex_intensity"] = None
            entry["allocation_pattern"] = None

            ratios_list.append(entry)

        result_df = pd.DataFrame(ratios_list)
        logger.info(f"Computed {len(result_df)} ratio rows across {result_df['company_id'].nunique()} companies")
        return result_df

    def store(self, df: pd.DataFrame) -> None:
        """Store computed ratios in financial_ratios table."""
        if df.empty:
            return

        # Build list of expected column names matching schema
        ratio_cols = [
            "company_id", "year",
            "net_profit_margin", "operating_profit_margin", "gross_profit_margin",
            "roe", "roce", "roa", "roic",
            "debt_to_equity", "interest_coverage", "net_debt", "net_debt_to_ebitda",
            "asset_turnover", "current_ratio", "quick_ratio",
            "inventory_turnover", "dividend_yield", "fcf_yield",
            "ev_to_ebitda", "pe_ratio", "pb_ratio",
            "cfo_quality", "capex_intensity", "allocation_pattern",
        ]

        # Ensure we have all expected columns
        store_df = df.copy()
        for col in ratio_cols:
            if col not in store_df.columns:
                store_df[col] = None

        # Select only cols matching schema
        avail = [c for c in ratio_cols if c in store_df.columns]
        store_df = store_df[avail]

        with self.engine.begin() as conn:
            # Delete all existing ratio data for re-computation
            conn.execute(text("DELETE FROM financial_ratios"))

        store_df.to_sql(
            "financial_ratios",
            self.engine,
            if_exists="append",
            index=False,
        )
        logger.info(f"Stored {len(store_df)} rows in financial_ratios")

    def run(self) -> dict:
        """Main entry point: compute all ratios and store them."""
        logger.info("Computing financial ratios...")
        df = self.compute_all()
        if not df.empty:
            self.store(df)

        # Also compute cash flow KPIs
        try:
            from src.analytics.cashflow_kpis import CashFlowAnalyzer
            cf_analyzer = CashFlowAnalyzer(db_path=self.db_path)
            cf_results = cf_analyzer.run()
            if not cf_results.empty and not df.empty:
                self._merge_cf_kpis(df, cf_results)
        except Exception as e:
            logger.warning(f"Cash-flow KPIs could not be computed: {e}")

        total = len(df)
        companies = df["company_id"].nunique() if not df.empty else 0
        logger.info(
            f"Ratio engine done: {total} rows across {companies} companies. "
            f"Financial warnings: {len(self.financial_warnings)}, "
            f"ICR warnings: {len(self.icr_warnings)}"
        )
        return {
            "total_rows": total,
            "companies": companies,
            "financial_warnings": len(self.financial_warnings),
            "icr_warnings": len(self.icr_warnings),
        }

    def _merge_cf_kpis(self, ratios_df: pd.DataFrame, cf_results: pd.DataFrame) -> None:
        """Merge cash flow KPIs into ratios table."""
        if cf_results.empty:
            return

        with self.engine.begin() as conn:
            for _, row in cf_results.iterrows():
                cid = int(row["company_id"])
                yr = int(row["year"])
                updates = {}
                if "cfo_quality" in row and row["cfo_quality"] is not None:
                    updates["cfo_quality"] = str(row["cfo_quality"])
                if "capex_intensity_label" in row and row["capex_intensity_label"] is not None:
                    updates["capex_intensity"] = str(row["capex_intensity_label"])
                if "allocation_pattern" in row and row["allocation_pattern"] is not None:
                    updates["allocation_pattern"] = str(row["allocation_pattern"])

                if updates:
                    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
                    params = {**updates, "cid": cid, "yr": yr}
                    conn.execute(
                        text(
                            f"UPDATE financial_ratios SET {set_clause} "
                            f"WHERE company_id = :cid AND year = :yr"
                        ),
                        params,
                    )


if __name__ == "__main__":
    engine = RatioEngine()
    result = engine.run()
    print(f"Done: {result}")
