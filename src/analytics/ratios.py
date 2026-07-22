"""Financial Ratio Engine — Sprint 2. Computes 20+ KPIs for all companies across all years."""

import os
import sqlite3
from collections import defaultdict
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


def nvl(val, default=0.0):
    return default if val is None or pd.isna(val) else val


# ── Standalone ratio functions (kept for backward-compatible unit tests) ────


def net_profit_margin(net_profit, sales) -> Optional[float]:
    if not sales or sales == 0:
        return None
    return (net_profit / sales) * 100


def operating_profit_margin(operating_profit, sales) -> Optional[float]:
    if not sales or sales == 0:
        return None
    return (operating_profit / sales) * 100


def return_on_equity(net_profit, equity_capital, reserves) -> Optional[float]:
    equity = (equity_capital or 0) + (reserves or 0)
    if equity <= 0:
        return None
    return (net_profit / equity) * 100


def return_on_capital_employed(ebit, equity_capital, reserves, borrowings) -> Optional[float]:
    capital = (equity_capital or 0) + (reserves or 0) + (borrowings or 0)
    if capital <= 0:
        return None
    return (ebit / capital) * 100


def return_on_assets(net_profit, total_assets) -> Optional[float]:
    if not total_assets or total_assets == 0:
        return None
    return (net_profit / total_assets) * 100


def debt_to_equity(borrowings, equity_capital, reserves) -> Optional[float]:
    equity = (equity_capital or 0) + (reserves or 0)
    if equity <= 0:
        return None
    if not borrowings or borrowings == 0:
        return 0.0
    return borrowings / equity


def interest_coverage_ratio(operating_profit, other_income, interest) -> Optional[float]:
    if not interest or interest == 0:
        return None
    ebit = (operating_profit or 0) + (other_income or 0)
    return ebit / interest


def net_debt(borrowings, investments) -> Optional[float]:
    b = borrowings or 0
    i = investments or 0
    return b - i


def asset_turnover(sales, total_assets) -> Optional[float]:
    if not total_assets or total_assets == 0:
        return None
    return sales / total_assets


# ── RatioEngine class ──────────────────────────────────────────────────────


class RatioEngine:
    def __init__(self, db_path="db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.financial_warnings = []
        self.icr_warnings = []
        self._companies = pd.DataFrame()

    def _is_financial(self, sector_name) -> bool:
        if not sector_name:
            return False
        s = str(sector_name).lower()
        return any(kw in s for kw in ["financial", "bfsi", "bank"])

    def compute_ratios(self, company_id=None):
        query = """
            SELECT p.company_id, p.year,
                p.sales, p.operating_profit, p.operating_profit_margin AS pl_opm,
                p.net_profit, p.eps, p.dividend_payout_pct, p.tax_rate,
                p.depreciation, p.interest_expense, p.other_income,
                p.total_revenue, p.cogs,
                b.total_assets, b.total_liabilities, b.shareholders_equity,
                b.total_debt, b.current_assets, b.current_liabilities,
                b.cash_and_equivalents, b.inventory,
                c.sector_name, c.market_cap, c.ticker
            FROM profitandloss p
            LEFT JOIN balancesheet b ON p.company_id = b.company_id AND p.year = b.year
            LEFT JOIN companies c ON p.company_id = c.company_id
        """
        params = {}
        if company_id is not None:
            query += " WHERE p.company_id = :cid"
            params["cid"] = company_id

        df = pd.read_sql_query(text(query), self.engine, params=params)

        if df.empty:
            return pd.DataFrame()

        ratios_list = []

        for _, row in df.iterrows():
            cid = int(row["company_id"])
            yr = int(row["year"])
            sector = row.get("sector_name")
            is_fin = self._is_financial(sector)

            entry = {"company_id": cid, "year": yr}

            sales = row.get("sales")
            net_profit = row.get("net_profit")
            op_profit = row.get("operating_profit")
            total_assets = row.get("total_assets")
            equity = row.get("shareholders_equity")
            total_debt = row.get("total_debt")
            cash = row.get("cash_and_equivalents")
            cur_assets = row.get("current_assets")
            cur_liab = row.get("current_liabilities")
            inventory = row.get("inventory")
            depreciation = row.get("depreciation")
            interest_expense = row.get("interest_expense")
            tax_rate = row.get("tax_rate")
            cogs = row.get("cogs")
            eps = row.get("eps")
            div_payout = row.get("dividend_payout_pct")
            mcap = row.get("market_cap")

            # net_profit_margin
            entry["net_profit_margin"] = (
                (net_profit / sales * 100) if sales and sales != 0 else None
            )

            # operating_profit_margin
            entry["operating_profit_margin"] = (
                (op_profit / sales * 100) if sales and sales != 0 else None
            )

            # gross_profit_margin
            if cogs is not None and sales and sales != 0:
                entry["gross_profit_margin"] = (sales - cogs) / sales * 100
            else:
                entry["gross_profit_margin"] = None

            # ROE
            entry["roe"] = (
                (net_profit / equity * 100)
                if equity and equity > 0
                else None
            )

            # ROCE
            denom_roce = total_assets - (cur_liab if cur_liab else 0) if total_assets else None
            entry["roce"] = (
                (op_profit / denom_roce * 100)
                if denom_roce and denom_roce > 0
                else None
            )

            # ROA
            entry["roa"] = (
                (net_profit / total_assets * 100)
                if total_assets and total_assets > 0
                else None
            )

            # ROIC
            invested_capital = (total_debt or 0) + (equity or 0)
            if invested_capital > 0:
                if tax_rate is not None and not pd.isna(tax_rate):
                    entry["roic"] = (op_profit * (1 - tax_rate / 100)) / invested_capital * 100
                else:
                    entry["roic"] = op_profit / invested_capital * 100
            else:
                entry["roic"] = None

            # debt_to_equity
            if equity is None or equity <= 0:
                entry["debt_to_equity"] = None
            elif total_debt is None or total_debt == 0:
                entry["debt_to_equity"] = 0.0
            else:
                entry["debt_to_equity"] = total_debt / equity

            # financial sector high-leverage flag
            if (
                is_fin
                and entry["debt_to_equity"] is not None
                and entry["debt_to_equity"] > 5
            ):
                self.financial_warnings.append(
                    f"{cid}:{yr} | Financial sector D/E={entry['debt_to_equity']:.2f} > 5"
                )

            # interest_coverage
            if interest_expense is None or interest_expense == 0:
                entry["interest_coverage"] = None
                if op_profit is not None:
                    self.icr_warnings.append(f"{cid}:{yr} | Debt Free (interest_expense=0)")
            else:
                entry["interest_coverage"] = op_profit / interest_expense
                if entry["interest_coverage"] < 1.5:
                    self.icr_warnings.append(
                        f"{cid}:{yr} | ICR={entry['interest_coverage']:.2f} < 1.5"
                    )

            # net_debt
            entry["net_debt"] = (total_debt or 0) - (cash or 0)

            # net_debt_to_ebitda
            ebitda = (op_profit or 0) + (depreciation or 0)
            nd = entry["net_debt"]
            entry["net_debt_to_ebitda"] = (
                nd / ebitda if ebitda > 0 else None
            )

            # asset_turnover
            entry["asset_turnover"] = (
                sales / total_assets
                if sales is not None and total_assets and total_assets != 0
                else None
            )

            # current_ratio
            entry["current_ratio"] = (
                cur_assets / cur_liab
                if cur_assets is not None and cur_liab and cur_liab != 0
                else None
            )

            # quick_ratio
            if cur_assets is not None and cur_liab and cur_liab != 0:
                entry["quick_ratio"] = (cur_assets - (inventory or 0)) / cur_liab
            else:
                entry["quick_ratio"] = None

            # dividend_yield: (div_payout_pct/100 * eps) / closing_price
            entry["dividend_yield"] = None
            if div_payout is not None and eps is not None and eps != 0:
                closing_price = None
                sp_query = """
                    SELECT close FROM stock_prices
                    WHERE company_id = :cid
                      AND CAST(substr(trade_date, 1, 4) AS INTEGER) = :yr
                    ORDER BY trade_date DESC LIMIT 1
                """
                sp_df = pd.read_sql_query(
                    text(sp_query), self.engine, params={"cid": cid, "yr": yr}
                )
                if not sp_df.empty:
                    closing_price = sp_df.iloc[0]["close"]
                if closing_price and closing_price != 0:
                    entry["dividend_yield"] = (
                        (div_payout / 100) * eps / closing_price * 100
                    )

            # fcf_yield: fcf / market_cap
            entry["fcf_yield"] = None
            cf_query = """
                SELECT fcf FROM cashflow
                WHERE company_id = :cid AND year = :yr
            """
            cf_df = pd.read_sql_query(
                text(cf_query), self.engine, params={"cid": cid, "yr": yr}
            )
            if not cf_df.empty:
                fcf_val = cf_df.iloc[0]["fcf"]
                if fcf_val is not None and mcap and mcap != 0:
                    entry["fcf_yield"] = fcf_val / mcap * 100

            # ev_to_ebitda — complex, return None
            entry["ev_to_ebitda"] = None

            # pe_ratio
            entry["pe_ratio"] = None
            if eps and eps != 0:
                sp_pe = pd.read_sql_query(
                    text(sp_query), self.engine, params={"cid": cid, "yr": yr}
                )
                if not sp_pe.empty:
                    cp = sp_pe.iloc[0]["close"]
                    if cp and cp != 0:
                        entry["pe_ratio"] = cp / eps

            # pb_ratio: market_cap / shareholders_equity
            entry["pb_ratio"] = (
                mcap / equity
                if mcap is not None and equity and equity > 0
                else None
            )

            ratios_list.append(entry)

        result_df = pd.DataFrame(ratios_list)
        return result_df

    def _store(self, df: pd.DataFrame):
        if df.empty:
            return

        table_cols = [
            "company_id", "year",
            "net_profit_margin", "operating_profit_margin", "gross_profit_margin",
            "roe", "roce", "roa", "roic",
            "debt_to_equity", "interest_coverage", "net_debt", "net_debt_to_ebitda",
            "asset_turnover", "current_ratio", "quick_ratio",
            "dividend_yield", "fcf_yield", "ev_to_ebitda", "pe_ratio", "pb_ratio",
        ]

        upsert_cols = [c for c in table_cols if c in df.columns]
        upsert_df = df[upsert_cols].copy()

        # Delete existing rows for the same (company_id, year) pairs before insert
        with self.engine.begin() as conn:
            for _, row in upsert_df.iterrows():
                conn.execute(
                    text(
                        "DELETE FROM financial_ratios WHERE company_id = :cid AND year = :yr"
                    ),
                    {"cid": int(row["company_id"]), "yr": int(row["year"])},
                )

        upsert_df.to_sql(
            "financial_ratios",
            self.engine,
            if_exists="append",
            index=False,
            dtype={
                "company_id": None,
                "year": None,
            },
        )

    def run(self):
        print("[RatioEngine] Computing financial ratios...")
        companies_df = pd.read_sql_query(
            text("SELECT company_id FROM companies"), self.engine
        )
        total_count = 0
        company_count = 0

        for _, crow in companies_df.iterrows():
            cid = int(crow["company_id"])
            ratios_df = self.compute_ratios(company_id=cid)
            if not ratios_df.empty:
                self._store(ratios_df)
                total_count += len(ratios_df)
            company_count += 1

        print(
            f"[RatioEngine] Computed {total_count} ratio rows across {company_count} companies"
        )
        print(
            f"[RatioEngine] Financial sector warnings: {len(self.financial_warnings)}"
        )
        print(f"[RatioEngine] ICR warnings: {len(self.icr_warnings)}")

        return {
            "total_rows": total_count,
            "companies": company_count,
            "financial_warnings": len(self.financial_warnings),
            "icr_warnings": len(self.icr_warnings),
        }


if __name__ == "__main__":
    engine = RatioEngine()
    result = engine.run()
    print(f"Done: {result}")
