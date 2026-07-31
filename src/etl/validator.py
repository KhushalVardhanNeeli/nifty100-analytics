import csv
import os
import re
from datetime import datetime


class DQValidator:

    def __init__(self, engine):
        self.engine = engine

    def _query(self, sql, params=None):
        import pandas as pd
        return pd.read_sql(sql, self.engine, params=params)

    def _execute(self, sql, params=None):
        import pandas as pd
        pd.read_sql(sql, self.engine, params=params)

    def _is_valid_url(self, url):
        if url is None:
            return True
        if not isinstance(url, str):
            return False
        if not url.strip():
            return True
        pattern = re.compile(
            r"^https?://[^\s/$.?#].[^\s]*$",
            re.IGNORECASE,
        )
        return bool(pattern.match(url.strip()))

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
        failures.extend(self.dq09_dividend_payout())
        failures.extend(self.dq10_valid_urls())
        failures.extend(self.dq11_eps_sign())
        failures.extend(self.dq12_ca_cl_balance())
        failures.extend(self.dq13_coverage())
        failures.extend(self.dq14_year_range())
        failures.extend(self.dq15_no_duplicate_tickers())
        failures.extend(self.dq16_market_cap_positive())
        return failures

    def dq01_pk_uniqueness(self):
        failures = []
        tables = {
            "companies": "company_id",
            "sectors": "sector_id",
            "profitandloss": "pnl_id",
            "balancesheet": "bs_id",
            "cashflow": "cf_id",
            "stock_prices": "sp_id",
            "analysis": "analysis_id",
            "documents": "doc_id",
            "financial_ratios": "fr_id",
            "peer_percentiles": "pp_id",
        }
        for table, pk in tables.items():
            try:
                df = self._query(
                    f'SELECT "{pk}" FROM "{table}"'
                )
                if df.empty:
                    continue
                total = len(df)
                unique = df[pk].nunique()
                if total != unique:
                    counts = df[pk].value_counts()
                    dupes = counts[counts > 1]
                    for pk_val, cnt in dupes.items():
                        failures.append({
                            "table": table,
                            "company_id": None,
                            "year": None,
                            "rule": "DQ-01",
                            "severity": "CRITICAL",
                            "message": (
                                f"Duplicate PK value {pk_val} found {cnt} times "
                                f"in table {table}"
                            ),
                        })
            except Exception as e:
                failures.append({
                    "table": table,
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-01",
                    "severity": "CRITICAL",
                    "message": f"Error checking DQ-01 for {table}: {e}",
                })
        return failures

    def dq02_composite_uniqueness(self):
        failures = []
        tables = ["profitandloss", "balancesheet", "cashflow"]
        for table in tables:
            try:
                df = self._query(
                    f'SELECT company_id, year FROM "{table}"'
                )
                if df.empty:
                    continue
                dupes = df[df.duplicated(subset=["company_id", "year"], keep=False)]
                if not dupes.empty:
                    grouped = dupes.groupby(["company_id", "year"]).size().reset_index(name="count")
                    for _, row in grouped.iterrows():
                        failures.append({
                            "table": table,
                            "company_id": int(row["company_id"]),
                            "year": int(row["year"]),
                            "rule": "DQ-02",
                            "severity": "CRITICAL",
                            "message": (
                                f"Duplicate (company_id={row['company_id']}, "
                                f"year={row['year']}) found {row['count']} "
                                f"times in {table}"
                            ),
                        })
            except Exception as e:
                failures.append({
                    "table": table,
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-02",
                    "severity": "CRITICAL",
                    "message": f"Error checking DQ-02 for {table}: {e}",
                })
        return failures

    def dq03_fk_integrity(self):
        failures = []
        try:
            cids = self._query('SELECT company_id FROM companies')
        except Exception:
            return failures
        if cids.empty:
            return failures
        valid_ids = set(cids["company_id"].dropna().astype(int).tolist())
        fk_tables = [
            "profitandloss", "balancesheet", "cashflow",
            "stock_prices", "analysis", "documents",
            "financial_ratios", "peer_percentiles",
        ]
        for table in fk_tables:
            try:
                df = self._query(
                    f'SELECT DISTINCT company_id FROM "{table}"'
                )
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    cid = row["company_id"]
                    if cid is not None and int(cid) not in valid_ids:
                        failures.append({
                            "table": table,
                            "company_id": int(cid),
                            "year": None,
                            "rule": "DQ-03",
                            "severity": "CRITICAL",
                            "message": (
                                f"FK violation: company_id={cid} in {table} "
                                f"does not exist in companies"
                            ),
                        })
            except Exception as e:
                failures.append({
                    "table": table,
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-03",
                    "severity": "CRITICAL",
                    "message": f"Error checking DQ-03 for {table}: {e}",
                })
        return failures

    def dq04_bs_balance(self):
        failures = []
        try:
            df = self._query(
                "SELECT bs_id, company_id, year, total_assets, "
                "total_liabilities, shareholders_equity FROM balancesheet"
            )
        except Exception as e:
            return [{
                "table": "balancesheet",
                "company_id": None,
                "year": None,
                "rule": "DQ-04",
                "severity": "CRITICAL",
                "message": f"Error checking DQ-04: {e}",
            }]
        if df.empty:
            return failures
        for _, row in df.iterrows():
            ta = row["total_assets"]
            tl = row["total_liabilities"]
            se = row["shareholders_equity"]
            if ta is None or tl is None:
                continue
            if ta == 0:
                continue

            # Two checks:
            # 1. A = L (total_liabilities column includes equity in this data format)
            diff_a_l = abs(ta - tl)
            if ta != 0 and diff_a_l / abs(ta) >= 0.01:
                # 2. Try A = (L - E) + E = L (same check)
                failures.append({
                    "table": "balancesheet",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-04",
                    "severity": "CRITICAL",
                    "message": (
                        f"BS imbalance: Assets={ta}, "
                        f"Liabilities={tl}, diff_pct={diff_a_l/abs(ta):.4%}"
                    ),
                })
        return failures

    def dq05_opm_cross_check(self):
        failures = []
        try:
            df = self._query(
                "SELECT pnl_id, company_id, year, operating_profit_margin, "
                "operating_profit, sales FROM profitandloss"
            )
        except Exception as e:
            return [{
                "table": "profitandloss",
                "company_id": None,
                "year": None,
                "rule": "DQ-05",
                "severity": "CRITICAL",
                "message": f"Error checking DQ-05: {e}",
            }]
        if df.empty:
            return failures
        for _, row in df.iterrows():
            opm_stored = row["operating_profit_margin"]
            op = row["operating_profit"]
            sales = row["sales"]
            if opm_stored is None or op is None or sales is None:
                continue
            if sales == 0:
                continue
            opm_calc = op / sales
            diff = abs(opm_stored - opm_calc)
            if diff >= 0.01:
                failures.append({
                    "table": "profitandloss",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-05",
                    "severity": "CRITICAL",
                    "message": (
                        f"OPM mismatch: stored={opm_stored:.4f}, "
                        f"calculated={opm_calc:.4f}, diff={diff:.4f}"
                    ),
                })
        return failures

    def dq06_positive_sales(self):
        failures = []
        try:
            df = self._query(
                "SELECT pnl_id, company_id, year, sales FROM profitandloss"
            )
        except Exception as e:
            return [{
                "table": "profitandloss",
                "company_id": None,
                "year": None,
                "rule": "DQ-06",
                "severity": "CRITICAL",
                "message": f"Error checking DQ-06: {e}",
            }]
        if df.empty:
            return failures
        for _, row in df.iterrows():
            sales = row["sales"]
            if sales is None:
                continue
            if sales <= 0:
                failures.append({
                    "table": "profitandloss",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-06",
                    "severity": "CRITICAL",
                    "message": f"Non-positive sales: {sales}",
                })
        return failures

    def dq07_net_cash(self):
        failures = []
        try:
            df = self._query(
                "SELECT bs_id, company_id, year, cash_and_equivalents "
                "FROM balancesheet"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            cash = row["cash_and_equivalents"]
            if cash is None:
                continue
            if cash < 0:
                failures.append({
                    "table": "balancesheet",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-07",
                    "severity": "WARNING",
                    "message": f"Negative cash and equivalents: {cash}",
                })
        return failures

    def dq08_tax_rate(self):
        failures = []
        try:
            df = self._query(
                "SELECT pnl_id, company_id, year, tax_rate FROM profitandloss"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            tr = row["tax_rate"]
            if tr is None:
                continue
            if tr < 0 or tr > 1.0:
                failures.append({
                    "table": "profitandloss",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-08",
                    "severity": "WARNING",
                    "message": f"Tax rate out of 0-100% range: {tr}",
                })
        return failures

    def dq09_dividend_payout(self):
        failures = []
        try:
            df = self._query(
                "SELECT pnl_id, company_id, year, dividend_payout_pct "
                "FROM profitandloss"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            dp = row["dividend_payout_pct"]
            if dp is None:
                continue
            if dp > 2.0:
                failures.append({
                    "table": "profitandloss",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-09",
                    "severity": "WARNING",
                    "message": f"Dividend payout exceeds 200% cap: {dp}",
                })
        return failures

    def dq10_valid_urls(self):
        failures = []
        try:
            df = self._query(
                "SELECT company_id, ticker, website FROM companies"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            website = row["website"]
            if website is None:
                continue
            if not self._is_valid_url(website):
                failures.append({
                    "table": "companies",
                    "company_id": int(row["company_id"]),
                    "year": None,
                    "rule": "DQ-10",
                    "severity": "WARNING",
                    "message": f"Invalid website URL: {website}",
                })
        return failures

    def dq11_eps_sign(self):
        failures = []
        try:
            df = self._query(
                "SELECT pnl_id, company_id, year, eps, net_profit "
                "FROM profitandloss"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            eps = row["eps"]
            np_val = row["net_profit"]
            if eps is None or np_val is None:
                continue
            if eps == 0 or np_val == 0:
                continue
            if (eps > 0 and np_val < 0) or (eps < 0 and np_val > 0):
                failures.append({
                    "table": "profitandloss",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-11",
                    "severity": "WARNING",
                    "message": (
                        f"EPS sign mismatch: EPS={eps}, Net Profit={np_val}"
                    ),
                })
        return failures

    def dq12_ca_cl_balance(self):
        failures = []
        try:
            df = self._query(
                "SELECT bs_id, company_id, year, current_assets, "
                "current_liabilities FROM balancesheet"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            ca = row["current_assets"]
            cl = row["current_liabilities"]
            if ca is None or cl is None:
                continue
            if ca < cl * 0.5:
                failures.append({
                    "table": "balancesheet",
                    "company_id": int(row["company_id"]),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "rule": "DQ-12",
                    "severity": "WARNING",
                    "message": (
                        f"Current assets ({ca}) significantly below "
                        f"current liabilities ({cl})"
                    ),
                })
        return failures

    def dq13_coverage(self):
        failures = []
        min_rows = {
            "companies": 1,
            "sectors": 1,
            "profitandloss": 10,
            "balancesheet": 10,
            "cashflow": 10,
            "stock_prices": 10,
            "analysis": 1,
            "documents": 1,
            "financial_ratios": 10,
            "peer_percentiles": 1,
        }
        for table, minimum in min_rows.items():
            try:
                df = self._query(f'SELECT COUNT(*) AS cnt FROM "{table}"')
                cnt = df["cnt"].iloc[0] if not df.empty else 0
            except Exception:
                cnt = 0
            if cnt < minimum:
                failures.append({
                    "table": table,
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-13",
                    "severity": "WARNING",
                    "message": (
                        f"Table {table} has {cnt} rows, "
                        f"minimum expected: {minimum}"
                    ),
                })
        return failures

    def dq14_year_range(self):
        failures = []
        year_tables = [
            "profitandloss", "balancesheet", "cashflow",
            "analysis", "financial_ratios", "peer_percentiles",
        ]
        for table in year_tables:
            try:
                df = self._query(
                    f'SELECT DISTINCT year FROM "{table}" WHERE year IS NOT NULL'
                )
            except Exception:
                continue
            if df.empty:
                continue
            for _, row in df.iterrows():
                yr = row["year"]
                if yr is None:
                    continue
                if yr < 1990 or yr > 2030:
                    failures.append({
                        "table": table,
                        "company_id": None,
                        "year": int(yr),
                        "rule": "DQ-14",
                        "severity": "WARNING",
                        "message": f"Year {yr} outside allowed range 1990-2030",
                    })
        return failures

    def dq15_no_duplicate_tickers(self):
        failures = []
        try:
            df = self._query("SELECT ticker FROM companies")
        except Exception as e:
            return [{
                "table": "companies",
                "company_id": None,
                "year": None,
                "rule": "DQ-15",
                "severity": "WARNING",
                "message": f"Error checking DQ-15: {e}",
            }]
        if df.empty:
            return failures
        dupes = df[df.duplicated(subset=["ticker"], keep=False)]
        if not dupes.empty:
            grouped = dupes.groupby("ticker").size().reset_index(name="count")
            for _, row in grouped.iterrows():
                failures.append({
                    "table": "companies",
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-15",
                    "severity": "WARNING",
                    "message": (
                        f"Duplicate ticker '{row['ticker']}' "
                        f"found {row['count']} times"
                    ),
                })
        return failures

    def dq16_market_cap_positive(self):
        failures = []
        try:
            df = self._query(
                "SELECT company_id, ticker, market_cap FROM companies"
            )
        except Exception:
            return failures
        if df.empty:
            return failures
        for _, row in df.iterrows():
            mc = row["market_cap"]
            if mc is None:
                continue
            if mc <= 0:
                failures.append({
                    "table": "companies",
                    "company_id": int(row["company_id"]),
                    "year": None,
                    "rule": "DQ-16",
                    "severity": "WARNING",
                    "message": (
                        f"Non-positive market cap for "
                        f"{row['ticker']}: {mc}"
                    ),
                })
        return failures

    def export_failures(self, failures, path):
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        if not failures:
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow([
                    "table", "company_id", "year",
                    "rule", "severity", "message",
                ])
            return
        fieldnames = ["table", "company_id", "year", "rule", "severity", "message"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(failures)
