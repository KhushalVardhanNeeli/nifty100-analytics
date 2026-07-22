import os
import csv
import glob
import pandas as pd
from sqlalchemy import create_engine, text

from src.etl.normaliser import (
    normalize_ticker,
    normalize_year,
    normalize_numeric,
    normalize_sector_name,
)
from src.etl.validator import DQValidator


class ETLPipeline:

    COLUMN_MAPS = {
        "companies": [
            "ticker", "company_name", "sector_name", "industry",
            "market_cap", "listing_status", "isin", "bse_code",
            "nse_symbol", "founded_year", "website",
        ],
        "pnl": [
            "company_id", "year", "sales", "operating_profit",
            "operating_profit_margin", "net_profit", "eps",
            "dividend_payout_pct", "tax_rate", "depreciation",
            "interest_expense", "other_income", "total_revenue",
            "cogs", "employee_cost",
        ],
        "bs": [
            "company_id", "year", "total_assets", "total_liabilities",
            "shareholders_equity", "total_debt", "current_assets",
            "current_liabilities", "cash_and_equivalents", "inventory",
            "trade_receivables", "investments", "fixed_assets",
            "intangible_assets", "borrowings_current",
            "borrowings_noncurrent",
        ],
        "cf": [
            "company_id", "year", "operating_activities",
            "investing_activities", "financing_activities",
            "net_cash_flow", "capex", "fcf", "dividends_paid",
        ],
        "stock_prices": [
            "company_id", "trade_date", "open", "high", "low",
            "close", "volume",
        ],
    }

    FILE_TYPE_SIGNATURES = {
        "companies": [
            "ticker", "company_name", "isin", "bse_code", "nse_symbol",
        ],
        "pnl": [
            "sales", "operating_profit", "net_profit", "cogs",
        ],
        "bs": [
            "total_assets", "total_liabilities", "shareholders_equity",
            "current_assets", "current_liabilities",
        ],
        "cf": [
            "operating_activities", "investing_activities",
            "financing_activities", "capex",
        ],
        "stock_prices": [
            "trade_date", "open", "high", "low", "close", "volume",
        ],
    }

    LOAD_ORDER = ["companies", "pnl", "bs", "cf", "stock_prices"]

    def __init__(self, data_dir="data/", db_path="db/nifty100.db"):
        self.data_dir = data_dir
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        self._init_schema()
        self.counts = {
            "companies": {"loaded": 0, "rejected": 0},
            "pnl": {"loaded": 0, "rejected": 0},
            "bs": {"loaded": 0, "rejected": 0},
            "cf": {"loaded": 0, "rejected": 0},
            "stock_prices": {"loaded": 0, "rejected": 0},
        }

    def _init_schema(self):
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "db", "schema.sql",
        )
        if not os.path.exists(schema_path):
            schema_path = os.path.join("db", "schema.sql")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(
                f"Schema file not found at {schema_path}. "
                f"Ensure db/schema.sql exists."
            )
        with open(schema_path, "r") as f:
            sql = f.read()
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        with self.engine.begin() as conn:
            for stmt in statements:
                if stmt:
                    conn.execute(text(stmt))

    @staticmethod
    def _load_file(path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(path)
        elif ext in (".xlsx",):
            df = pd.read_excel(path, engine="openpyxl")
        elif ext in (".xls",):
            df = pd.read_excel(path, engine="xlrd")
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.to_dict(orient="records")

    def _normalize_company(self, row):
        return {
            "ticker": normalize_ticker(row.get("ticker")),
            "company_name": str(row.get("company_name", "")).strip() or row.get("company_name"),
            "sector_name": normalize_sector_name(row.get("sector_name")),
            "industry": row.get("industry"),
            "market_cap": normalize_numeric(row.get("market_cap")),
            "listing_status": str(row.get("listing_status", "Active")).strip() or "Active",
            "isin": row.get("isin"),
            "bse_code": row.get("bse_code"),
            "nse_symbol": row.get("nse_symbol"),
            "founded_year": normalize_year(row.get("founded_year")),
            "website": row.get("website"),
        }

    def _normalize_pnl(self, row):
        return {
            "company_id": row.get("company_id"),
            "year": normalize_year(row.get("year")),
            "sales": normalize_numeric(row.get("sales")),
            "operating_profit": normalize_numeric(row.get("operating_profit")),
            "operating_profit_margin": normalize_numeric(row.get("operating_profit_margin")),
            "net_profit": normalize_numeric(row.get("net_profit")),
            "eps": normalize_numeric(row.get("eps")),
            "dividend_payout_pct": normalize_numeric(row.get("dividend_payout_pct")),
            "tax_rate": normalize_numeric(row.get("tax_rate")),
            "depreciation": normalize_numeric(row.get("depreciation")),
            "interest_expense": normalize_numeric(row.get("interest_expense")),
            "other_income": normalize_numeric(row.get("other_income")),
            "total_revenue": normalize_numeric(row.get("total_revenue")),
            "cogs": normalize_numeric(row.get("cogs")),
            "employee_cost": normalize_numeric(row.get("employee_cost")),
        }

    def _normalize_bs(self, row):
        return {
            "company_id": row.get("company_id"),
            "year": normalize_year(row.get("year")),
            "total_assets": normalize_numeric(row.get("total_assets")),
            "total_liabilities": normalize_numeric(row.get("total_liabilities")),
            "shareholders_equity": normalize_numeric(row.get("shareholders_equity")),
            "total_debt": normalize_numeric(row.get("total_debt")),
            "current_assets": normalize_numeric(row.get("current_assets")),
            "current_liabilities": normalize_numeric(row.get("current_liabilities")),
            "cash_and_equivalents": normalize_numeric(row.get("cash_and_equivalents")),
            "inventory": normalize_numeric(row.get("inventory")),
            "trade_receivables": normalize_numeric(row.get("trade_receivables")),
            "investments": normalize_numeric(row.get("investments")),
            "fixed_assets": normalize_numeric(row.get("fixed_assets")),
            "intangible_assets": normalize_numeric(row.get("intangible_assets")),
            "borrowings_current": normalize_numeric(row.get("borrowings_current")),
            "borrowings_noncurrent": normalize_numeric(row.get("borrowings_noncurrent")),
        }

    def _normalize_cf(self, row):
        return {
            "company_id": row.get("company_id"),
            "year": normalize_year(row.get("year")),
            "operating_activities": normalize_numeric(row.get("operating_activities")),
            "investing_activities": normalize_numeric(row.get("investing_activities")),
            "financing_activities": normalize_numeric(row.get("financing_activities")),
            "net_cash_flow": normalize_numeric(row.get("net_cash_flow")),
            "capex": normalize_numeric(row.get("capex")),
            "fcf": normalize_numeric(row.get("fcf")),
            "dividends_paid": normalize_numeric(row.get("dividends_paid")),
        }

    def _normalize_stock(self, row):
        trade_date = row.get("trade_date")
        if trade_date is not None:
            trade_date = str(trade_date).strip()
        return {
            "company_id": row.get("company_id"),
            "trade_date": trade_date,
            "open": normalize_numeric(row.get("open")),
            "high": normalize_numeric(row.get("high")),
            "low": normalize_numeric(row.get("low")),
            "close": normalize_numeric(row.get("close")),
            "volume": row.get("volume"),
        }

    def _infer_file_type(self, columns):
        columns_lower = set(c.lower().strip() for c in columns)
        scores = {}
        for ftype, sig_cols in self.FILE_TYPE_SIGNATURES.items():
            score = sum(1 for c in sig_cols if c in columns_lower)
            if score > 0:
                scores[ftype] = score
        if not scores:
            return None
        return max(scores, key=scores.get)

    def _get_company_id_map(self):
        try:
            df = pd.read_sql("SELECT company_id, ticker FROM companies", self.engine)
            return dict(zip(df["ticker"].str.upper(), df["company_id"]))
        except Exception:
            return {}

    def _resolve_company_id(self, row, file_type):
        cid = row.get("company_id")
        if cid is not None:
            return cid
        ticker = normalize_ticker(row.get("ticker"))
        if ticker:
            company_map = self._get_company_id_map()
            return company_map.get(ticker)
        return None

    def _load_by_type(self, file_type, rows, columns):
        table_map = {
            "companies": "companies",
            "pnl": "profitandloss",
            "bs": "balancesheet",
            "cf": "cashflow",
            "stock_prices": "stock_prices",
        }
        normalizer_map = {
            "companies": self._normalize_company,
            "pnl": self._normalize_pnl,
            "bs": self._normalize_bs,
            "cf": self._normalize_cf,
            "stock_prices": self._normalize_stock,
        }
        table = table_map[file_type]
        normalizer = normalizer_map[file_type]
        normalized_rows = []
        rejected = 0
        company_map = self._get_company_id_map() if file_type != "companies" else {}
        for row in rows:
            try:
                norm = normalizer(row)
                if file_type != "companies" and norm.get("company_id") is None:
                    ticker = normalize_ticker(row.get("ticker"))
                    if ticker and ticker in company_map:
                        norm["company_id"] = company_map[ticker]
                    else:
                        rejected += 1
                        continue
                normalized_rows.append(norm)
            except Exception:
                rejected += 1
        if not normalized_rows:
            self.counts[file_type]["rejected"] += rejected
            return
        df = pd.DataFrame(normalized_rows)
        expected_cols = self.COLUMN_MAPS[file_type]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
        df = df[[c for c in expected_cols if c in df.columns]]
        try:
            df.to_sql(
                table,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )
            self.counts[file_type]["loaded"] += len(df)
        except Exception as e:
            print(f"Error inserting into {table}: {e}")
            self.counts[file_type]["rejected"] += len(df)

    def _export_audit(self):
        os.makedirs("output", exist_ok=True)
        path = "output/load_audit.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["table", "loaded", "rejected"])
            for t in self.LOAD_ORDER:
                writer.writerow([t, self.counts[t]["loaded"], self.counts[t]["rejected"]])

    def run(self):
        patterns = ["*.csv", "*.xlsx", "*.xls"]
        files = []
        for pat in patterns:
            files.extend(glob.glob(os.path.join(self.data_dir, pat)))
        if not files:
            print(f"No data files found in {self.data_dir}")
            return
        file_types = []
        for fpath in files:
            try:
                raw_rows = self._load_file(fpath)
                if not raw_rows:
                    continue
                columns = list(raw_rows[0].keys())
                ftype = self._infer_file_type(columns)
                if ftype is None:
                    print(f"Warning: Could not infer file type for {fpath}, skipping.")
                    continue
                file_types.append((ftype, fpath))
            except Exception as e:
                print(f"Error reading {fpath}: {e}")
        order_map = {t: i for i, t in enumerate(self.LOAD_ORDER)}
        file_types.sort(key=lambda x: order_map.get(x[0], 99))
        for ftype, fpath in file_types:
            rows = self._load_file(fpath)
            if not rows:
                continue
            self._load_by_type(ftype, rows, list(rows[0].keys()))
        self._export_audit()
        print("Load complete. Running validators...")
        validator = DQValidator(self.engine)
        failures = validator.run_all()
        validator.export_failures(failures, "output/validation_failures.csv")
        total_failures = len(failures)
        critical = sum(1 for f in failures if f["severity"] == "CRITICAL")
        warnings = sum(1 for f in failures if f["severity"] == "WARNING")
        print(
            f"Validation: {total_failures} failures "
            f"({critical} critical, {warnings} warnings)"
        )
        print("Audit: output/load_audit.csv")
        print("Validation failures: output/validation_failures.csv")
