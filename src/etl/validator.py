"""Data Quality Validator — 16 rules (DQ-01 .. DQ-16).

Severity policy (per project spec):
  * CRITICAL — PK/FK integrity (DQ-01, DQ-02, DQ-03). Must be zero before load.
  * WARNING  — everything else (OPM, balance, sales, etc.). Documented, not blocking.

Each rule returns a list of failure dicts with keys:
  rule, severity, table, field, company_id, year, issue.
"""

import csv
import os
import re


class DQValidator:
    """Runs all 16 data-quality rules against the SQLite database."""

    def __init__(self, engine):
        self.engine = engine

    def _query(self, sql, params=None):
        import pandas as pd
        return pd.read_sql(sql, self.engine, params=params)

    def _is_valid_url(self, url):
        if url is None:
            return True
        if not isinstance(url, str):
            return False
        if not url.strip():
            return True
        pattern = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
        return bool(pattern.match(url.strip()))

    # ── Orchestration ────────────────────────────────────────────────

    def run_all(self):
        failures = []
        failures.extend(self.dq01_pk_uniqueness())
        failures.extend(self.dq02_composite_uniqueness())
        failures.extend(self.dq03_fk_integrity())
        failures.extend(self.dq04_bs_balance())
        failures.extend(self.dq05_opm_cross_check())
        failures.extend(self.dq06_positive_sales())
        failures.extend(self.dq07_net_cash())
        failures.extend(self.dq08_tax_rate())
        failures.extend(self.dq09_dividend_cap())
        failures.extend(self.dq10_valid_urls())
        failures.extend(self.dq11_eps_sign())
        failures.extend(self.dq12_bs_equity_balance())
        failures.extend(self.dq13_coverage())
        failures.extend(self.dq14_year_range())
        failures.extend(self.dq15_no_duplicate_tickers())
        failures.extend(self.dq16_market_cap_positive())
        return failures

    def _fail(self, rule, severity, table, field, company_id, year, issue):
        return {
            "rule": rule,
            "severity": severity,
            "table": table,
            "field": field,
            "company_id": company_id,
            "year": year,
            "issue": issue,
        }

    # ── CRITICAL rules ───────────────────────────────────────────────

    def dq01_pk_uniqueness(self):
        """DQ-01 — primary key uniqueness for every table (CRITICAL)."""
        failures = []
        pks = {
            "companies": "company_id",
            "sectors": "sector_id",
            "profitandloss": "pnl_id",
            "balancesheet": "bs_id",
            "cashflow": "cf_id",
            "stock_prices": "sp_id",
            "analysis": "analysis_id",
            "documents": "doc_id",
            "prosandcons": "pc_id",
            "financial_ratios": "fr_id",
            "peer_groups": "pg_id",
            "market_cap": "mc_id",
        }
        for table, pk in pks.items():
            try:
                df = self._query(f'SELECT "{pk}" AS pk FROM "{table}"')
            except Exception as e:
                failures.append(self._fail("DQ-01", "CRITICAL", table, pk, None, None,
                                           f"Error checking DQ-01: {e}"))
                continue
            if df.empty:
                continue
            dupes = df[df.duplicated(subset=["pk"], keep=False)]
            if not dupes.empty:
                for pk_val in dupes["pk"].drop_duplicates().tolist():
                    cnt = int((df["pk"] == pk_val).sum())
                    failures.append(self._fail(
                        "DQ-01", "CRITICAL", table, pk, None, None,
                        f"Duplicate PK value {pk_val} found {cnt} times in {table}",
                    ))
        return failures

    def dq02_composite_uniqueness(self):
        """DQ-02 — (company_id, year) uniqueness in fact tables (CRITICAL)."""
        failures = []
        for table in ["profitandloss", "balancesheet", "cashflow", "financial_ratios", "market_cap"]:
            try:
                df = self._query(f'SELECT company_id, year FROM "{table}"')
            except Exception as e:
                failures.append(self._fail("DQ-02", "CRITICAL", table, "company_id,year", None, None,
                                           f"Error checking DQ-02: {e}"))
                continue
            if df.empty:
                continue
            dupes = df[df.duplicated(subset=["company_id", "year"], keep=False)]
            for _, row in dupes.groupby(["company_id", "year"]).size().reset_index(name="count").iterrows():
                failures.append(self._fail(
                    "DQ-02", "CRITICAL", table, "company_id,year",
                    int(row["company_id"]), int(row["year"]),
                    f"Duplicate (company_id={row['company_id']}, year={row['year']}) found {row['count']} times",
                ))
        return failures

    def dq03_fk_integrity(self):
        """DQ-03 — foreign key integrity (CRITICAL)."""
        failures = []
        try:
            companies = self._query("SELECT company_id FROM companies")
        except Exception:
            return failures
        if companies.empty:
            return failures
        valid = set(companies["company_id"].dropna().astype(int).tolist())
        for table in ["profitandloss", "balancesheet", "cashflow", "stock_prices",
                      "analysis", "documents", "prosandcons", "financial_ratios",
                      "peer_groups", "market_cap"]:
            try:
                df = self._query(f'SELECT DISTINCT company_id FROM "{table}"')
            except Exception:
                continue
            for _, row in df.iterrows():
                cid = row["company_id"]
                if cid is not None and int(cid) not in valid:
                    failures.append(self._fail(
                        "DQ-03", "CRITICAL", table, "company_id", int(cid), None,
                        f"FK violation: company_id={cid} not in companies",
                    ))
        return failures

    # ── WARNING rules ────────────────────────────────────────────────

    def dq04_bs_balance(self):
        """DQ-04 — balance sheet balance: total_assets ≈ total_liabilities (<1%)."""
        failures = []
        try:
            df = self._query("SELECT bs_id, company_id, year, total_assets, total_liabilities "
                             "FROM balancesheet")
        except Exception as e:
            return [self._fail("DQ-04", "WARNING", "balancesheet", "total_assets", None, None,
                               f"Error checking DQ-04: {e}")]
        for _, row in df.iterrows():
            ta, tl = row["total_assets"], row["total_liabilities"]
            if ta is None or tl is None or ta == 0:
                continue
            if abs(ta - tl) / abs(ta) >= 0.01:
                failures.append(self._fail(
                    "DQ-04", "WARNING", "balancesheet", "total_assets",
                    int(row["company_id"]), row["year"],
                    f"BS imbalance: assets={ta}, liabilities={tl}, diff={abs(ta - tl) / abs(ta):.4%}",
                ))
        return failures

    def dq05_opm_cross_check(self):
        """DQ-05 — OPM cross-check: opm_percentage vs operating_profit/sales (>1% diff)."""
        failures = []
        try:
            df = self._query("SELECT pnl_id, company_id, year, opm_percentage, "
                             "operating_profit, sales FROM profitandloss")
        except Exception as e:
            return [self._fail("DQ-05", "WARNING", "profitandloss", "opm_percentage", None, None,
                               f"Error checking DQ-05: {e}")]
        for _, row in df.iterrows():
            opm, op, sales = row["opm_percentage"], row["operating_profit"], row["sales"]
            if opm is None or op is None or sales is None or sales == 0:
                continue
            # Normalise to a ratio: percent form (>1 in magnitude) -> /100.
            stored = opm / 100.0 if abs(opm) > 1 else opm
            calc = op / sales
            if abs(stored - calc) >= 0.01:
                failures.append(self._fail(
                    "DQ-05", "WARNING", "profitandloss", "opm_percentage",
                    int(row["company_id"]), row["year"],
                    f"OPM mismatch: source={opm}, calc={calc:.4f}, diff={abs(stored - calc):.4f}",
                ))
        return failures

    def dq06_positive_sales(self):
        """DQ-06 — sales must be positive."""
        failures = []
        try:
            df = self._query("SELECT pnl_id, company_id, year, sales FROM profitandloss")
        except Exception as e:
            return [self._fail("DQ-06", "WARNING", "profitandloss", "sales", None, None,
                               f"Error checking DQ-06: {e}")]
        for _, row in df.iterrows():
            if row["sales"] is not None and row["sales"] <= 0:
                failures.append(self._fail(
                    "DQ-06", "WARNING", "profitandloss", "sales",
                    int(row["company_id"]), row["year"], f"Non-positive sales: {row['sales']}",
                ))
        return failures

    def dq07_net_cash(self):
        """DQ-07 — net cash flow must be present for reported cash-flow rows."""
        failures = []
        try:
            df = self._query("SELECT cf_id, company_id, year, operating_activity, "
                             "investing_activity, financing_activity, net_cash_flow FROM cashflow")
        except Exception as e:
            return [self._fail("DQ-07", "WARNING", "cashflow", "net_cash_flow", None, None,
                               f"Error checking DQ-07: {e}")]
        for _, row in df.iterrows():
            has_activity = any(row[c] is not None for c in
                               ["operating_activity", "investing_activity", "financing_activity"])
            if has_activity and row["net_cash_flow"] is None:
                failures.append(self._fail(
                    "DQ-07", "WARNING", "cashflow", "net_cash_flow",
                    int(row["company_id"]), row["year"], "net_cash_flow missing for reported activities",
                ))
        return failures

    def dq08_tax_rate(self):
        """DQ-08 — tax rate within 0-100%."""
        failures = []
        try:
            df = self._query("SELECT pnl_id, company_id, year, tax_percentage FROM profitandloss")
        except Exception:
            return failures
        for _, row in df.iterrows():
            tr = row["tax_percentage"]
            if tr is not None and (tr < 0 or tr > 100):
                failures.append(self._fail(
                    "DQ-08", "WARNING", "profitandloss", "tax_percentage",
                    int(row["company_id"]), row["year"], f"Tax rate out of 0-100% range: {tr}",
                ))
        return failures

    def dq09_dividend_cap(self):
        """DQ-09 — dividend payout cap (≤200%)."""
        failures = []
        try:
            df = self._query("SELECT pnl_id, company_id, year, dividend_payout FROM profitandloss")
        except Exception:
            return failures
        for _, row in df.iterrows():
            dp = row["dividend_payout"]
            if dp is not None and dp > 200:
                failures.append(self._fail(
                    "DQ-09", "WARNING", "profitandloss", "dividend_payout",
                    int(row["company_id"]), row["year"], f"Dividend payout exceeds 200% cap: {dp}",
                ))
        return failures

    def dq10_valid_urls(self):
        """DQ-10 — website URLs must be well-formed."""
        failures = []
        try:
            df = self._query("SELECT company_id, ticker, website FROM companies")
        except Exception:
            return failures
        for _, row in df.iterrows():
            if row["website"] is not None and not self._is_valid_url(row["website"]):
                failures.append(self._fail(
                    "DQ-10", "WARNING", "companies", "website",
                    int(row["company_id"]), None, f"Invalid website URL: {row['website']}",
                ))
        return failures

    def dq11_eps_sign(self):
        """DQ-11 — EPS sign must agree with net profit sign."""
        failures = []
        try:
            df = self._query("SELECT pnl_id, company_id, year, eps, net_profit FROM profitandloss")
        except Exception:
            return failures
        for _, row in df.iterrows():
            eps, np_ = row["eps"], row["net_profit"]
            if eps is None or np_ is None or eps == 0 or np_ == 0:
                continue
            if (eps > 0 and np_ < 0) or (eps < 0 and np_ > 0):
                failures.append(self._fail(
                    "DQ-11", "WARNING", "profitandloss", "eps",
                    int(row["company_id"]), row["year"],
                    f"EPS sign mismatch: EPS={eps}, net_profit={np_}",
                ))
        return failures

    def dq12_bs_equity_balance(self):
        """DQ-12 — balance sheet components must reconcile to total_liabilities."""
        failures = []
        try:
            df = self._query("SELECT bs_id, company_id, year, equity_capital, reserves, "
                             "borrowings, other_liabilities, total_liabilities FROM balancesheet")
        except Exception:
            return failures
        for _, row in df.iterrows():
            tl = row["total_liabilities"]
            if tl is None or tl == 0:
                continue
            comps = sum(v for v in [row["equity_capital"], row["reserves"],
                                    row["borrowings"], row["other_liabilities"]] if v is not None)
            if abs(comps - tl) / abs(tl) >= 0.01:
                failures.append(self._fail(
                    "DQ-12", "WARNING", "balancesheet", "equity_capital",
                    int(row["company_id"]), row["year"],
                    f"BS components ({comps}) don't reconcile with total_liabilities ({tl})",
                ))
        return failures

    def dq13_coverage(self):
        """DQ-13 — minimum row coverage per table."""
        failures = []
        minimums = {
            "companies": 1, "sectors": 1, "profitandloss": 10,
            "balancesheet": 10, "cashflow": 10, "stock_prices": 10,
            "analysis": 1, "documents": 1, "prosandcons": 1,
            "financial_ratios": 10, "peer_groups": 1, "market_cap": 1,
        }
        for table, minimum in minimums.items():
            try:
                cnt = self._query(f'SELECT COUNT(*) AS cnt FROM "{table}"')["cnt"].iloc[0]
            except Exception:
                cnt = 0
            if cnt < minimum:
                failures.append(self._fail(
                    "DQ-13", "WARNING", table, "row_count", None, None,
                    f"Table {table} has {cnt} rows, minimum expected {minimum}",
                ))
        return failures

    def dq14_year_range(self):
        """DQ-14 — year values within 1990-2030."""
        failures = []
        for table in ["profitandloss", "balancesheet", "cashflow", "financial_ratios", "market_cap", "documents"]:
            try:
                df = self._query(f'SELECT DISTINCT year FROM "{table}" WHERE year IS NOT NULL')
            except Exception:
                continue
            for _, row in df.iterrows():
                yr = row["year"]
                if yr is not None and (yr < 1990 or yr > 2030):
                    failures.append(self._fail(
                        "DQ-14", "WARNING", table, "year", None, int(yr),
                        f"Year {yr} outside allowed range 1990-2030",
                    ))
        return failures

    def dq15_no_duplicate_tickers(self):
        """DQ-15 — company tickers must be unique."""
        failures = []
        try:
            df = self._query("SELECT ticker FROM companies")
        except Exception:
            return failures
        if df.empty:
            return failures
        dupes = df[df.duplicated(subset=["ticker"], keep=False)]
        for ticker in dupes["ticker"].drop_duplicates().tolist():
            cnt = int((df["ticker"] == ticker).sum())
            failures.append(self._fail(
                "DQ-15", "WARNING", "companies", "ticker", None, None,
                f"Duplicate ticker '{ticker}' found {cnt} times",
            ))
        return failures

    def dq16_market_cap_positive(self):
        """DQ-16 — market cap must be positive."""
        failures = []
        try:
            df = self._query("SELECT company_id, ticker, market_cap_crore FROM companies")
        except Exception:
            return failures
        for _, row in df.iterrows():
            mc = row["market_cap_crore"]
            if mc is not None and mc <= 0:
                failures.append(self._fail(
                    "DQ-16", "WARNING", "companies", "market_cap_crore",
                    int(row["company_id"]), None,
                    f"Non-positive market cap for {row['ticker']}: {mc}",
                ))
        return failures

    # ── Export ──────────────────────────────────────────────────────

    def export_failures(self, failures, path):
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        fieldnames = ["company_id", "field", "issue", "severity", "rule", "year", "table"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            if failures:
                writer.writerows(failures)
