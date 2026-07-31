"""ETL Pipeline — Nifty 100 Financial Intelligence Platform.

Loads data from Excel files in data/raw/ and data/supporting/, normalises columns,
merges sector data, creates ticker-to-company_id mapping, and populates SQLite.
"""

import csv
import logging
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

from src.etl.normaliser import normalize_ticker, normalize_year, normalize_numeric

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etl")


def _extract_years_from_string(s: str) -> Optional[int]:
    """Extract the first 4-digit year from a string like 'Dec 2012' or 'Mar-13'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        if pd.isna(s):
            return None
        y = int(s)
        return y if 1900 <= y <= 2100 else None
    s = str(s).strip()
    match = re.search(r"(19[0-9]{2}|20[0-9]{2}|2100)", s)
    if match:
        return int(match.group(0))
    return None


class ETLPipeline:
    """Orchestrates data loading from raw Excel files into SQLite."""

    RAW_HEADER_ROW = 1
    SUPP_HEADER_ROW = 0

    def __init__(self, data_dir: str = "data/", db_path: str = "db/nifty100.db"):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        self._init_schema()
        self._ticker_to_id: dict[str, int] = {}
        self.counts: dict[str, dict[str, int]] = {}

    def _init_schema(self) -> None:
        schema_path = self.db_path.parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        with open(schema_path) as f:
            sql = f.read()
        with self.engine.begin() as conn:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _load_excel(self, path: Path, header_row: int = 0) -> pd.DataFrame:
        df = pd.read_excel(path, engine="openpyxl", header=header_row)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        # Drop completely empty rows
        df = df.dropna(how="all")
        return df

    def _make_ticker_map(self) -> dict[str, int]:
        if self._ticker_to_id:
            return self._ticker_to_id
        try:
            df = pd.read_sql("SELECT company_id, ticker FROM companies", self.engine)
            self._ticker_to_id = dict(
                zip(df["ticker"].str.upper().str.strip(), df["company_id"])
            )
        except Exception:
            self._ticker_to_id = {}
        return self._ticker_to_id

    def _resolve_company_id(self, ticker: Optional[str]) -> Optional[int]:
        if ticker is None:
            return None
        t = normalize_ticker(ticker)
        if not t:
            return None
        mapping = self._make_ticker_map()
        return mapping.get(t)

    def _load_years(self, df: pd.DataFrame, col: str = "year") -> pd.Series:
        """Extract numeric years from string column like 'Dec 2012'."""
        return df[col].apply(_extract_years_from_string)

    # ── Phase 1: Companies ───────────────────────────────────────────────

    def load_companies(self) -> None:
        """Load companies.xlsx and sectors.xlsx, build companies table."""
        path = self.data_dir / "raw" / "companies.xlsx"
        if not path.exists():
            logger.warning("companies.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        logger.info(f"companies.xlsx: {len(df)} rows")

        # Map columns
        result = []
        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("id"))
            if not ticker:
                continue
            result.append({
                "ticker": ticker,
                "company_name": str(row.get("company_name", "")).strip(),
                "sector_name": None,  # filled in later
                "industry": None,
                "market_cap": None,
                "listing_status": "Active",
                "isin": None,
                "bse_code": str(row.get("bse_profile", "")).strip() or None,
                "nse_symbol": str(row.get("nse_profile", "")).strip() or None,
                "founded_year": None,
                "website": str(row.get("website", "")).strip() or None,
            })

        result_df = pd.DataFrame(result)
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM companies"))
        result_df.to_sql("companies", self.engine, if_exists="append", index=False)
        self.counts["companies"] = {"loaded": len(result_df), "rejected": 0}
        logger.info(f"Loaded {len(result_df)} companies")

    def load_sectors_and_link(self) -> None:
        """Load sectors.xlsx and update companies with sector names."""
        path = self.data_dir / "supporting" / "sectors.xlsx"
        if not path.exists():
            logger.warning("sectors.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.SUPP_HEADER_ROW)
        logger.info(f"sectors.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                ticker = normalize_ticker(row.get("company_id"))
                if not ticker or ticker not in ticker_map:
                    continue
                cid = ticker_map[ticker]
                sector = str(row.get("broad_sector", "")).strip()
                sub_sector = str(row.get("sub_sector", "")).strip()
                market_cat = str(row.get("market_cap_category", "")).strip()
                index_wt = row.get("index_weight_pct")

                conn.execute(
                    text(
                        "UPDATE companies SET sector_name = :sector, industry = :sub, "
                        "listing_status = :mcat WHERE company_id = :cid"
                    ),
                    {"sector": sector, "sub": sub_sector, "mcat": market_cat, "cid": cid},
                )

        # Also populate sectors table
        sector_names = (
            self._load_excel(path, header_row=self.SUPP_HEADER_ROW)["broad_sector"]
            .dropna()
            .unique()
        )
        sector_df = pd.DataFrame(
            [{"sector_name": s} for s in sector_names if s.strip()]
        )
        if not sector_df.empty:
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM sectors"))
            sector_df.to_sql("sectors", self.engine, if_exists="append", index=False)
        logger.info(f"Linked sectors to companies, {len(sector_df)} unique sectors")

    def load_market_cap(self) -> None:
        """Load market_cap.xlsx and update companies with latest market cap."""
        path = self.data_dir / "supporting" / "market_cap.xlsx"
        if not path.exists():
            logger.warning("market_cap.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.SUPP_HEADER_ROW)
        logger.info(f"market_cap.xlsx: {len(df)} rows")
        ticker_map = self._make_ticker_map()

        # Use the most recent year's market_cap for each company
        latest = (
            df.sort_values("year", ascending=False)
            .groupby("company_id")
            .first()
            .reset_index()
        )

        mcap_records = []
        with self.engine.begin() as conn:
            for _, row in latest.iterrows():
                ticker = normalize_ticker(row.get("company_id"))
                if not ticker or ticker not in ticker_map:
                    continue
                cid = ticker_map[ticker]
                mcap = row.get("market_cap_crore")
                ev = row.get("enterprise_value_crore")

                mcap_records.append({
                    "company_id": cid,
                    "year": int(row["year"]) if pd.notna(row.get("year")) else None,
                    "market_cap_crore": float(mcap) if pd.notna(mcap) else None,
                    "enterprise_value_crore": float(ev) if pd.notna(ev) else None,
                    "pe_ratio": float(row["pe_ratio"]) if pd.notna(row.get("pe_ratio")) else None,
                    "pb_ratio": float(row["pb_ratio"]) if pd.notna(row.get("pb_ratio")) else None,
                    "ev_ebitda": float(row["ev_ebitda"]) if pd.notna(row.get("ev_ebitda")) else None,
                    "dividend_yield_pct": float(row["dividend_yield_pct"]) if pd.notna(row.get("dividend_yield_pct")) else None,
                })

                conn.execute(
                    text("UPDATE companies SET market_cap = :mcap WHERE company_id = :cid"),
                    {"mcap": float(mcap) if pd.notna(mcap) else None, "cid": cid},
                )

        if mcap_records:
            mcap_df = pd.DataFrame(mcap_records)
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM market_cap_annual"))
            mcap_df.to_sql("market_cap_annual", self.engine, if_exists="append", index=False)

        logger.info(f"Loaded market cap for {len(mcap_records)} companies")

    # ── Phase 2: Financial Statements ────────────────────────────────────

    def load_profitandloss(self) -> None:
        path = self.data_dir / "raw" / "profitandloss.xlsx"
        if not path.exists():
            logger.warning("profitandloss.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        logger.info(f"profitandloss.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        records, rejected = [], 0

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                rejected += 1
                continue

            yr = _extract_years_from_string(row.get("year"))
            if yr is None:
                rejected += 1
                continue

            rec = {
                "company_id": cid,
                "year": yr,
                "sales": float(row["sales"]) if pd.notna(row.get("sales")) else None,
                "operating_profit": float(row["operating_profit"]) if pd.notna(row.get("operating_profit")) else None,
                "operating_profit_margin": (
                    float(row["opm_percentage"]) / 100 if pd.notna(row.get("opm_percentage")) else None
                ),
                "net_profit": float(row["net_profit"]) if pd.notna(row.get("net_profit")) else None,
                "eps": float(row["eps"]) if pd.notna(row.get("eps")) else None,
                "dividend_payout_pct": (
                    float(row["dividend_payout"]) / 100 if pd.notna(row.get("dividend_payout")) else None
                ),
                "tax_rate": (
                    float(row["tax_percentage"]) / 100 if pd.notna(row.get("tax_percentage")) else None
                ),
                "depreciation": float(row["depreciation"]) if pd.notna(row.get("depreciation")) else None,
                "interest_expense": float(row.get("interest", row.get("interest_expense"))) if pd.notna(row.get("interest", row.get("interest_expense", pd.NA))) else None,
                "other_income": float(row["other_income"]) if pd.notna(row.get("other_income")) else None,
                "total_revenue": float(row["sales"]) if pd.notna(row.get("sales")) else None,
                "cogs": float(row["expenses"]) if pd.notna(row.get("expenses")) else None,
                "employee_cost": None,
            }
            records.append(rec)

        result_df = pd.DataFrame(records)
        result_df = result_df.drop_duplicates(subset=["company_id", "year"], keep="first")
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM profitandloss"))
        result_df.to_sql("profitandloss", self.engine, if_exists="append", index=False)
        self.counts["pnl"] = {"loaded": len(result_df), "rejected": rejected}
        logger.info(f"Loaded {len(result_df)} P&L rows, {rejected} rejected")

    def load_balancesheet(self) -> None:
        path = self.data_dir / "raw" / "balancesheet.xlsx"
        if not path.exists():
            logger.warning("balancesheet.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        logger.info(f"balancesheet.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        records, rejected = [], 0

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                rejected += 1
                continue

            yr = _extract_years_from_string(row.get("year"))
            if yr is None:
                rejected += 1
                continue

            equity = float(row.get("equity_capital") or 0)
            reserves = float(row.get("reserves") or 0)
            borrowings = float(row.get("borrowings") or 0)
            other_liab = float(row.get("other_liabilities") or 0)

            rec = {
                "company_id": cid,
                "year": yr,
                "total_assets": float(row["total_assets"]) if pd.notna(row.get("total_assets")) else None,
                "total_liabilities": float(row["total_liabilities"]) if pd.notna(row.get("total_liabilities")) else None,
                "shareholders_equity": equity + reserves,
                "total_debt": borrowings,
                "current_assets": None,
                "current_liabilities": None,
                "cash_and_equivalents": None,
                "inventory": None,
                "trade_receivables": None,
                "investments": float(row["investments"]) if pd.notna(row.get("investments")) else None,
                "fixed_assets": float(row["fixed_assets"]) if pd.notna(row.get("fixed_assets")) else None,
                "intangible_assets": None,
                "borrowings_current": borrowings,
                "borrowings_noncurrent": None,
            }
            records.append(rec)

        result_df = pd.DataFrame(records)
        result_df = result_df.drop_duplicates(subset=["company_id", "year"], keep="first")
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM balancesheet"))
        result_df.to_sql("balancesheet", self.engine, if_exists="append", index=False)
        self.counts["bs"] = {"loaded": len(result_df), "rejected": rejected}
        logger.info(f"Loaded {len(result_df)} BS rows, {rejected} rejected")

    def load_cashflow(self) -> None:
        path = self.data_dir / "raw" / "cashflow.xlsx"
        if not path.exists():
            logger.warning("cashflow.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        logger.info(f"cashflow.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        records, rejected = [], 0

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                rejected += 1
                continue

            yr = _extract_years_from_string(row.get("year"))
            if yr is None:
                rejected += 1
                continue

            oa = float(row.get("operating_activity") or 0)
            ia = float(row.get("investing_activity") or 0)
            fa = float(row.get("financing_activity") or 0)

            rec = {
                "company_id": cid,
                "year": yr,
                "operating_activities": oa,
                "investing_activities": ia,
                "financing_activities": fa,
                "net_cash_flow": float(row["net_cash_flow"]) if pd.notna(row.get("net_cash_flow")) else (oa + ia + fa),
                "capex": abs(ia) if ia < 0 else 0,  # capex is typically negative investing cf
                "fcf": oa + ia,
                "dividends_paid": None,
            }
            records.append(rec)

        result_df = pd.DataFrame(records)
        result_df = result_df.drop_duplicates(subset=["company_id", "year"], keep="first")
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM cashflow"))
        result_df.to_sql("cashflow", self.engine, if_exists="append", index=False)
        self.counts["cf"] = {"loaded": len(result_df), "rejected": rejected}
        logger.info(f"Loaded {len(result_df)} CF rows, {rejected} rejected")

    # ── Phase 3: Supporting Data ─────────────────────────────────────────

    def load_stock_prices(self) -> None:
        path = self.data_dir / "supporting" / "stock_prices.xlsx"
        if not path.exists():
            logger.warning("stock_prices.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.SUPP_HEADER_ROW)
        logger.info(f"stock_prices.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        records, rejected = [], 0

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                rejected += 1
                continue

            rec = {
                "company_id": cid,
                "trade_date": str(row.get("date", "")).strip(),
                "open": float(row["open_price"]) if pd.notna(row.get("open_price")) else None,
                "high": float(row["high_price"]) if pd.notna(row.get("high_price")) else None,
                "low": float(row["low_price"]) if pd.notna(row.get("low_price")) else None,
                "close": float(row.get("close_price", row.get("adjusted_close"))) if pd.notna(row.get("close_price", row.get("adjusted_close", pd.NA))) else None,
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
            }
            records.append(rec)

        result_df = pd.DataFrame(records)
        result_df = result_df.drop_duplicates(subset=["company_id", "trade_date"], keep="first")
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM stock_prices"))
        result_df.to_sql("stock_prices", self.engine, if_exists="append", index=False)
        self.counts["stock_prices"] = {"loaded": len(result_df), "rejected": rejected}
        logger.info(f"Loaded {len(result_df)} stock price rows, {rejected} rejected")

    def load_documents(self) -> None:
        path = self.data_dir / "raw" / "documents.xlsx"
        if not path.exists():
            logger.warning("documents.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        logger.info(f"documents.xlsx: {len(df)} rows")

        ticker_map = self._make_ticker_map()
        records = []

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                continue

            yr_col = None
            for col in df.columns:
                if col in ("year", "yr"):
                    yr_val = row.get(col)
                    if pd.notna(yr_val) and yr_val != "Null":
                        try:
                            yr_col = int(float(yr_val))
                        except (ValueError, TypeError):
                            yr_col = str(yr_val).strip()
                    break
            if yr_col is None:
                yr_col = row.get("year", row.get("Year"))

            url = None
            for col in df.columns:
                if "annual" in col.lower() or "report" in col.lower():
                    url = row.get(col)
                    if pd.notna(url) and str(url).strip() and str(url).strip() != "Null":
                        url = str(url).strip()
                    else:
                        url = None
                    break

            if url:
                doc_name = f"{ticker}_Annual_Report_{yr_col or ''}"
                records.append({
                    "company_id": cid,
                    "doc_type": "Annual_Report",
                    "doc_name": doc_name[:255],
                    "file_path": url[:500],
                })

        if records:
            doc_df = pd.DataFrame(records).drop_duplicates(
                subset=["company_id", "doc_type", "doc_name"]
            )
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM documents"))
            doc_df.to_sql("documents", self.engine, if_exists="append", index=False)
        logger.info(f"Loaded {len(records)} document references")

    def load_analysis(self) -> None:
        path = self.data_dir / "raw" / "analysis.xlsx"
        if not path.exists():
            logger.warning("analysis.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        ticker_map = self._make_ticker_map()
        records = []

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                continue

            for col in [c for c in df.columns if c not in ("id", "company_id")]:
                val = row.get(col)
                if pd.isna(val) or not str(val).strip():
                    continue
                # Try to extract percentage values from strings like "10 Years: 21%"
                num_val = None
                desc = str(val).strip()
                match = re.search(r"(\d+\.?\d*)\s*%", desc)
                if match:
                    num_val = float(match.group(1))
                records.append({
                    "company_id": cid,
                    "year": None,
                    "analysis_type": "PRE_COMPUTED",
                    "metric_name": col,
                    "metric_value": num_val,
                    "description": desc,
                })

        if records:
            analysis_df = pd.DataFrame(records)
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM analysis"))
            analysis_df.to_sql("analysis", self.engine, if_exists="append", index=False)
        logger.info(f"Loaded {len(records)} analysis records")

    def load_prosandcons(self) -> None:
        path = self.data_dir / "raw" / "prosandcons.xlsx"
        if not path.exists():
            return

        df = self._load_excel(path, header_row=self.RAW_HEADER_ROW)
        ticker_map = self._make_ticker_map()
        records = []

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                continue
            records.append({
                "company_id": cid,
                "ticker": ticker,
                "pros": str(row.get("pros", "")) if pd.notna(row.get("pros")) else "",
                "cons": str(row.get("cons", "")) if pd.notna(row.get("cons")) else "",
            })

        if records:
            proscons_df = pd.DataFrame(records)
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM prosandcons"))
            proscons_df.to_sql("prosandcons", self.engine, if_exists="append", index=False)
        logger.info(f"Loaded {len(records)} pros/cons records")

    def load_peer_groups(self) -> None:
        path = self.data_dir / "supporting" / "peer_groups.xlsx"
        if not path.exists():
            logger.warning("peer_groups.xlsx not found")
            return

        df = self._load_excel(path, header_row=self.SUPP_HEADER_ROW)
        ticker_map = self._make_ticker_map()
        records = []

        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve_company_id(ticker)
            if cid is None:
                continue
            records.append({
                "company_id": cid,
                "peer_group_name": str(row.get("peer_group_name", "")).strip(),
                "is_benchmark": bool(row.get("is_benchmark", False)),
            })

        if records:
            peer_df = pd.DataFrame(records)
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM peer_group_mapping"))
            peer_df.to_sql("peer_group_mapping", self.engine, if_exists="append", index=False)
        logger.info(f"Loaded {len(records)} peer group mappings")

    # ── Run ───────────────────────────────────────────────────────────────

    def _export_audit(self) -> None:
        os.makedirs("output", exist_ok=True)
        path = "output/load_audit.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["table", "loaded", "rejected"])
            for t, cnt in self.counts.items():
                writer.writerow([t, cnt.get("loaded", 0), cnt.get("rejected", 0)])

    def run(self) -> None:
        logger.info("=== ETL Pipeline Starting ===")

        # Phase 1: Companies
        self.load_companies()
        self.load_sectors_and_link()
        self.load_market_cap()

        # Phase 2: Financial statements
        self.load_profitandloss()
        self.load_balancesheet()
        self.load_cashflow()

        # Phase 3: Supporting data
        self.load_stock_prices()
        self.load_documents()
        self.load_analysis()
        self.load_prosandcons()
        self.load_peer_groups()

        self._export_audit()
        logger.info("=== ETL Pipeline Complete ===")

        # Run validation
        from src.etl.validator import DQValidator
        logger.info("Running validators...")
        validator = DQValidator(self.engine)
        failures = validator.run_all()
        validator.export_failures(failures, "output/validation_failures.csv")
        total = len(failures)
        critical = sum(1 for f in failures if f.get("severity") == "CRITICAL")
        warnings = sum(1 for f in failures if f.get("severity") == "WARNING")
        logger.info(f"Validation: {total} failures ({critical} critical, {warnings} warnings)")

        # Quick stats
        try:
            cc = pd.read_sql("SELECT COUNT(*) as cnt FROM companies", self.engine).iloc[0]["cnt"]
            pl = pd.read_sql("SELECT COUNT(*) as cnt FROM profitandloss", self.engine).iloc[0]["cnt"]
            bs = pd.read_sql("SELECT COUNT(*) as cnt FROM balancesheet", self.engine).iloc[0]["cnt"]
            cf = pd.read_sql("SELECT COUNT(*) as cnt FROM cashflow", self.engine).iloc[0]["cnt"]
            sp = pd.read_sql("SELECT COUNT(*) as cnt FROM stock_prices", self.engine).iloc[0]["cnt"]
            logger.info(
                f"DB summary: {cc} companies, {pl} P&L rows, "
                f"{bs} BS rows, {cf} CF rows, {sp} stock prices"
            )
        except Exception as e:
            logger.warning(f"Could not get summary: {e}")


if __name__ == "__main__":
    pipeline = ETLPipeline()
    pipeline.run()
