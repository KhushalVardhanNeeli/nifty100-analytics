"""ETL Pipeline — Nifty 100 Financial Analytics (spec-aligned).

Loads 12 source files (7 core + 5 supplementary) into a 12-table SQLite
database. Handles:
  * 2-digit fiscal years ("Mar-13" -> 2013)
  * "TTM" rows (excluded, logged as rejected)
  * 9 extra companies present in the financial statements but absent from
    companies.xlsx / sectors.xlsx / market_cap.xlsx (added so FK=0)
  * duplicate (company_id, year) rows (deduped, keep-first)
"""

import csv
import logging
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, text

from src.etl.normaliser import normalize_ticker, normalize_year

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etl")

# 9 tickers found in the financial statements but missing from the reference
# files. Best-effort company names so FK integrity is preserved across all tables.
EXTRA_COMPANY_NAMES = {
    "AGTL": "Adani Total Gas Ltd",
    "ULTRACEMCO": "UltraTech Cement Ltd",
    "UNIONBANK": "Union Bank of India",
    "UNITDSPR": "United Spirits Ltd",
    "VBL": "Varun Beverages Ltd",
    "VEDL": "Vedanta Ltd",
    "WIPRO": "Wipro Ltd",
    "ZOMATO": "Zomato Ltd",
    "ZYDUSLIFE": "Zydus Lifesciences Ltd",
}

RAW_HEADER_ROW = 1
SUPP_HEADER_ROW = 0

TABLES = [
    "companies", "sectors", "profitandloss", "balancesheet", "cashflow",
    "analysis", "documents", "prosandcons", "stock_prices",
    "financial_ratios", "peer_groups", "market_cap",
]

# Drop order: children before parents so foreign-key constraints never break.
DROP_ORDER = [
    "profitandloss", "balancesheet", "cashflow", "stock_prices",
    "analysis", "documents", "prosandcons", "financial_ratios",
    "peer_groups", "market_cap",
    "companies", "sectors",
]


def _f(v):
    """Coerce a scalar to float, or None if NaN/None."""
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


class ETLPipeline:
    """Orchestrates loading raw Excel files into SQLite."""

    def __init__(self, data_dir: str = "data/", db_path: str = "db/nifty100.db"):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")

        @event.listens_for(self.engine, "connect")
        def _fk_on(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        self._ticker_to_id: dict[str, int] = {}
        self.counts: dict[str, dict] = {}
        self._init_schema()

    # ── Schema ───────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        schema_path = self.db_path.parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        sql = schema_path.read_text()
        # Use a raw sqlite3 connection with foreign_keys OFF so we can drop any
        # leftover tables (including older-schema tables) regardless of FK order.
        import sqlite3
        raw = sqlite3.connect(str(self.db_path))
        try:
            raw.execute("PRAGMA foreign_keys=OFF")
            rows = raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for (name,) in rows:
                raw.execute(f'DROP TABLE IF EXISTS "{name}"')
            raw.commit()
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    raw.execute(stmt)
            raw.commit()
        finally:
            raw.close()

    def _load_excel(self, path: Path, header_row: int = 0) -> pd.DataFrame:
        df = pd.read_excel(path, engine="openpyxl", header=header_row)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df = df.dropna(how="all")
        return df

    def _ticker_map(self) -> dict[str, int]:
        if self._ticker_to_id:
            return self._ticker_to_id
        df = pd.read_sql("SELECT company_id, ticker FROM companies", self.engine)
        self._ticker_to_id = {t: int(i) for t, i in zip(df["ticker"].str.upper().str.strip(), df["company_id"])}
        return self._ticker_to_id

    def _resolve(self, ticker):
        t = normalize_ticker(ticker)
        return self._ticker_map().get(t) if t else None

    def _load_many(self, table, records):
        if not records:
            return
        df = pd.DataFrame(records)
        df.to_sql(table, self.engine, if_exists="append", index=False)

    # ── Phase 1: Companies + reference data ──────────────────────────

    def load_companies(self) -> None:
        path = self.data_dir / "raw" / "companies.xlsx"
        df = self._load_excel(path, header_row=RAW_HEADER_ROW)
        records = []
        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("id"))
            if not ticker:
                continue
            records.append({
                "ticker": ticker,
                "company_name": str(row.get("company_name", "") or "").strip() or None,
                "about_company": str(row.get("about_company", "") or "").strip() or None,
                "website": str(row.get("website", "") or "").strip() or None,
                "nse_symbol": str(row.get("nse_profile", "") or "").strip() or None,
                "bse_code": str(row.get("bse_profile", "") or "").strip() or None,
                "face_value": _f(row.get("face_value")),
                "book_value": _f(row.get("book_value")),
                "roe_percentage": _f(row.get("roe_percentage")),
                "roce_percentage": _f(row.get("roce_percentage")),
            })
        self._load_many("companies", records)
        self.counts["companies"] = {"loaded": len(records), "rejected": 0}
        logger.info(f"Loaded {len(records)} companies from companies.xlsx")

    def _extra_tickers(self) -> set:
        """Discover tickers in financial statements not yet in companies."""
        known = set(self._ticker_map().keys()) if self._ticker_to_id else {
            normalize_ticker(t) for t in pd.read_sql("SELECT ticker FROM companies", self.engine)["ticker"]
        }
        found = set()
        for name in ["profitandloss", "balancesheet", "cashflow"]:
            p = self.data_dir / "raw" / f"{name}.xlsx"
            if not p.exists():
                continue
            d = self._load_excel(p, header_row=RAW_HEADER_ROW)
            if "company_id" in d.columns:
                for v in d["company_id"].dropna().unique():
                    t = normalize_ticker(v)
                    if t and t not in known:
                        found.add(t)
        return found

    def load_extra_companies(self) -> None:
        extras = self._extra_tickers()
        if not extras:
            return
        records = []
        for ticker in sorted(extras):
            records.append({
                "ticker": ticker,
                "company_name": EXTRA_COMPANY_NAMES.get(ticker, ticker),
            })
        self._load_many("companies", records)
        self.counts["extra_companies"] = {"loaded": len(records), "rejected": 0}
        logger.info(f"Added {len(records)} extra companies not in reference files: {sorted(extras)}")

    def load_sectors(self) -> None:
        path = self.data_dir / "supporting" / "sectors.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=SUPP_HEADER_ROW)
        ticker_map = self._ticker_map()
        sector_names = []
        updates = []
        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            broad = str(row.get("broad_sector", "") or "").strip()
            sub = str(row.get("sub_sector", "") or "").strip()
            if broad:
                sector_names.append(broad)
            cid = ticker_map.get(ticker) if ticker else None
            if cid is not None:
                updates.append({
                    "company_id": cid,
                    "broad_sector": broad or None,
                    "sub_sector": sub or None,
                    "index_weight_pct": _f(row.get("index_weight_pct")),
                    "market_cap_category": str(row.get("market_cap_category", "") or "").strip() or None,
                })
        with self.engine.begin() as conn:
            for u in updates:
                conn.execute(text(
                    "UPDATE companies SET broad_sector=:b, sub_sector=:s, "
                    "index_weight_pct=:w, market_cap_category=:m WHERE company_id=:c"
                ), {"b": u["broad_sector"], "s": u["sub_sector"],
                    "w": u["index_weight_pct"], "m": u["market_cap_category"], "c": u["company_id"]})
        unique = sorted({s for s in sector_names if s})
        self._load_many("sectors", [{"sector_name": s} for s in unique])
        self.counts["sectors"] = {"loaded": len(unique), "rejected": 0}
        logger.info(f"Linked sectors for {len(updates)} companies; {len(unique)} unique sectors")

    def load_market_cap(self) -> None:
        path = self.data_dir / "supporting" / "market_cap.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=SUPP_HEADER_ROW)
        ticker_map = self._ticker_map()
        records = []
        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = ticker_map.get(ticker) if ticker else None
            if cid is None:
                continue
            year = normalize_year(row.get("year"))
            records.append({
                "company_id": cid,
                "year": year,
                "market_cap_crore": _f(row.get("market_cap_crore")),
                "enterprise_value_crore": _f(row.get("enterprise_value_crore")),
                "pe_ratio": _f(row.get("pe_ratio")),
                "pb_ratio": _f(row.get("pb_ratio")),
                "ev_ebitda": _f(row.get("ev_ebitda")),
                "dividend_yield_pct": _f(row.get("dividend_yield_pct")),
            })
        rec_df = pd.DataFrame(records).drop_duplicates(subset=["company_id", "year"], keep="first")
        rec_df.to_sql("market_cap", self.engine, if_exists="append", index=False)

        latest = rec_df.sort_values("year").groupby("company_id").tail(1)
        with self.engine.begin() as conn:
            for _, row in latest.iterrows():
                conn.execute(text("UPDATE companies SET market_cap_crore=:m WHERE company_id=:c"),
                             {"m": row["market_cap_crore"], "c": int(row["company_id"])})
        self.counts["market_cap"] = {"loaded": len(rec_df), "rejected": 0}
        logger.info(f"Loaded market_cap: {len(rec_df)} rows")

    # ── Phase 2: Financial statements ────────────────────────────────

    def _load_financial(self, table, filename, row_map):
        path = self.data_dir / "raw" / f"{filename}.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=RAW_HEADER_ROW)
        records, rejected = [], 0
        for _, row in df.iterrows():
            ticker = normalize_ticker(row.get("company_id"))
            cid = self._resolve(ticker)
            year = normalize_year(row.get("year"))
            if cid is None or year is None:
                rejected += 1
                continue
            rec = row_map(row, cid, year)
            if rec is not None:
                records.append(rec)
        rec_df = pd.DataFrame(records).drop_duplicates(subset=["company_id", "year"], keep="first")
        rec_df.to_sql(table, self.engine, if_exists="append", index=False)
        self.counts[table] = {"loaded": len(rec_df), "rejected": rejected}
        logger.info(f"Loaded {len(rec_df)} {table} rows, {rejected} rejected")

    def load_profitandloss(self) -> None:
        def mapper(row, cid, year):
            return {
                "company_id": cid, "year": year,
                "sales": _f(row.get("sales")), "expenses": _f(row.get("expenses")),
                "operating_profit": _f(row.get("operating_profit")),
                "opm_percentage": _f(row.get("opm_percentage")),
                "other_income": _f(row.get("other_income")), "interest": _f(row.get("interest")),
                "depreciation": _f(row.get("depreciation")),
                "profit_before_tax": _f(row.get("profit_before_tax")),
                "tax_percentage": _f(row.get("tax_percentage")),
                "net_profit": _f(row.get("net_profit")), "eps": _f(row.get("eps")),
                "dividend_payout": _f(row.get("dividend_payout")),
            }
        self._load_financial("profitandloss", "profitandloss", mapper)

    def load_balancesheet(self) -> None:
        def mapper(row, cid, year):
            return {
                "company_id": cid, "year": year,
                "equity_capital": _f(row.get("equity_capital")), "reserves": _f(row.get("reserves")),
                "borrowings": _f(row.get("borrowings")), "other_liabilities": _f(row.get("other_liabilities")),
                "total_liabilities": _f(row.get("total_liabilities")), "fixed_assets": _f(row.get("fixed_assets")),
                "cwip": _f(row.get("cwip")), "investments": _f(row.get("investments")),
                "other_asset": _f(row.get("other_asset")), "total_assets": _f(row.get("total_assets")),
            }
        self._load_financial("balancesheet", "balancesheet", mapper)

    def load_cashflow(self) -> None:
        def mapper(row, cid, year):
            return {
                "company_id": cid, "year": year,
                "operating_activity": _f(row.get("operating_activity")),
                "investing_activity": _f(row.get("investing_activity")),
                "financing_activity": _f(row.get("financing_activity")),
                "net_cash_flow": _f(row.get("net_cash_flow")),
            }
        self._load_financial("cashflow", "cashflow", mapper)

    # ── Phase 3: Supplementary data ──────────────────────────────────

    def load_stock_prices(self) -> None:
        path = self.data_dir / "supporting" / "stock_prices.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=SUPP_HEADER_ROW)
        records, rejected = [], 0
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            if cid is None:
                rejected += 1
                continue
            records.append({
                "company_id": cid,
                "date": str(row.get("date", "") or "").strip(),
                "open_price": _f(row.get("open_price")), "high_price": _f(row.get("high_price")),
                "low_price": _f(row.get("low_price")), "close_price": _f(row.get("close_price")),
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "adjusted_close": _f(row.get("adjusted_close")),
            })
        rec_df = pd.DataFrame(records).drop_duplicates(subset=["company_id", "date"], keep="first")
        rec_df.to_sql("stock_prices", self.engine, if_exists="append", index=False)
        self.counts["stock_prices"] = {"loaded": len(rec_df), "rejected": rejected}
        logger.info(f"Loaded {len(rec_df)} stock_prices rows, {rejected} rejected")

    def load_documents(self) -> None:
        path = self.data_dir / "raw" / "documents.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=RAW_HEADER_ROW)
        records = []
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            if cid is None:
                continue
            url = row.get("annual_report")
            if url is None or pd.isna(url) or not str(url).strip():
                continue
            records.append({
                "company_id": cid,
                "year": normalize_year(row.get("year")),
                "annual_report": str(url).strip()[:500],
            })
        rec_df = pd.DataFrame(records).drop_duplicates(subset=["company_id", "year"], keep="first")
        rec_df.to_sql("documents", self.engine, if_exists="append", index=False)
        self.counts["documents"] = {"loaded": len(rec_df), "rejected": 0}
        logger.info(f"Loaded {len(rec_df)} document references")

    def load_analysis(self) -> None:
        path = self.data_dir / "raw" / "analysis.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=RAW_HEADER_ROW)
        records = []
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            if cid is None:
                continue
            records.append({
                "company_id": cid,
                "compounded_sales_growth": str(row.get("compounded_sales_growth", "") or "") or None,
                "compounded_profit_growth": str(row.get("compounded_profit_growth", "") or "") or None,
                "stock_price_cagr": str(row.get("stock_price_cagr", "") or "") or None,
                "roe": str(row.get("roe", "") or "") or None,
            })
        self._load_many("analysis", records)
        self.counts["analysis"] = {"loaded": len(records), "rejected": 0}
        logger.info(f"Loaded {len(records)} analysis records")

    def load_prosandcons(self) -> None:
        path = self.data_dir / "raw" / "prosandcons.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=RAW_HEADER_ROW)
        records = []
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            if cid is None:
                continue
            records.append({
                "company_id": cid,
                "pros": str(row.get("pros", "") or "") or None,
                "cons": str(row.get("cons", "") or "") or None,
            })
        self._load_many("prosandcons", records)
        self.counts["prosandcons"] = {"loaded": len(records), "rejected": 0}
        logger.info(f"Loaded {len(records)} pros/cons records")

    def load_financial_ratios(self) -> None:
        path = self.data_dir / "supporting" / "financial_ratios.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=SUPP_HEADER_ROW)
        cols = ["net_profit_margin_pct", "operating_profit_margin_pct", "return_on_equity_pct",
                "debt_to_equity", "interest_coverage", "asset_turnover", "free_cash_flow_cr",
                "capex_cr", "earnings_per_share", "book_value_per_share",
                "dividend_payout_ratio_pct", "total_debt_cr", "cash_from_operations_cr"]
        records, rejected = [], 0
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            year = normalize_year(row.get("year"))
            if cid is None or year is None:
                rejected += 1
                continue
            rec = {"company_id": cid, "year": year}
            for c in cols:
                rec[c] = _f(row.get(c))
            records.append(rec)
        rec_df = pd.DataFrame(records).drop_duplicates(subset=["company_id", "year"], keep="first")
        rec_df.to_sql("financial_ratios", self.engine, if_exists="append", index=False)
        self.counts["financial_ratios"] = {"loaded": len(rec_df), "rejected": rejected}
        logger.info(f"Loaded {len(rec_df)} financial_ratios rows, {rejected} rejected")

    def load_peer_groups(self) -> None:
        path = self.data_dir / "supporting" / "peer_groups.xlsx"
        if not path.exists():
            return
        df = self._load_excel(path, header_row=SUPP_HEADER_ROW)
        records = []
        for _, row in df.iterrows():
            cid = self._resolve(row.get("company_id"))
            if cid is None:
                continue
            records.append({
                "peer_group_name": str(row.get("peer_group_name", "") or "").strip(),
                "company_id": cid,
                "is_benchmark": bool(row.get("is_benchmark", False)),
            })
        self._load_many("peer_groups", records)
        self.counts["peer_groups"] = {"loaded": len(records), "rejected": 0}
        logger.info(f"Loaded {len(records)} peer group mappings")

    # ── Audit + run ──────────────────────────────────────────────────

    def _export_audit(self) -> None:
        os.makedirs("output", exist_ok=True)
        with open("output/load_audit.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["table", "loaded", "rejected"])
            for t, cnt in self.counts.items():
                writer.writerow([t, cnt.get("loaded", 0), cnt.get("rejected", 0)])

    def run(self) -> None:
        logger.info("=== ETL Pipeline Starting ===")

        self.load_companies()
        self.load_extra_companies()
        self.load_sectors()
        self.load_market_cap()

        self.load_profitandloss()
        self.load_balancesheet()
        self.load_cashflow()

        self.load_stock_prices()
        self.load_documents()
        self.load_analysis()
        self.load_prosandcons()
        self.load_financial_ratios()
        self.load_peer_groups()

        self._export_audit()

        from src.etl.validator import DQValidator
        validator = DQValidator(self.engine)
        failures = validator.run_all()
        validator.export_failures(failures, "output/validation_failures.csv")
        critical = sum(1 for f in failures if f.get("severity") == "CRITICAL")
        warnings = sum(1 for f in failures if f.get("severity") == "WARNING")
        logger.info(f"Validation: {len(failures)} failures ({critical} CRITICAL, {warnings} WARNING)")

        for t in TABLES:
            try:
                n = pd.read_sql(f'SELECT COUNT(*) AS c FROM "{t}"', self.engine)["c"].iloc[0]
                logger.info(f"  {t}: {n} rows")
            except Exception:
                pass
        fk = pd.read_sql("PRAGMA foreign_key_check", self.engine)
        logger.info(f"foreign_key_check: {len(fk)} violations")
        logger.info("=== ETL Pipeline Complete ===")


if __name__ == "__main__":
    ETLPipeline().run()
