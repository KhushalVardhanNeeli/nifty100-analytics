import math
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.etl.normaliser import (
    normalize_ticker,
    normalize_year,
    normalize_numeric,
    normalize_sector_name,
)
from src.etl.validator import DQValidator


# ── Helper ────────────────────────────────────────────────────────────────────

def _mkv(query_results):
    v = DQValidator.__new__(DQValidator)
    v.engine = MagicMock()
    v._query = MagicMock(side_effect=list(query_results) if not callable(query_results) else query_results)
    return v


def _empty_df():
    return pd.DataFrame()


def _empty_df_cols(*cols):
    return pd.DataFrame(columns=list(cols))


# ══════════════════════════════════════════════════════════════════════════════
# normalize_ticker — 8 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeTicker:
    def test_normal_ticker_uppercase(self):
        assert normalize_ticker("reliance") == "RELIANCE"

    def test_ticker_with_whitespace(self):
        assert normalize_ticker("  tcs  ") == "TCS"

    def test_ticker_with_leading_dot(self):
        assert normalize_ticker(".INFY") == "INFY"

    def test_ticker_with_trailing_dot(self):
        assert normalize_ticker("TCS.") == "TCS"

    def test_ticker_none(self):
        assert normalize_ticker(None) is None

    def test_ticker_nan(self):
        assert normalize_ticker(float("nan")) is None

    def test_ticker_empty_string(self):
        assert normalize_ticker("") is None

    def test_ticker_numeric_input(self):
        assert normalize_ticker(123) == "123"


# ══════════════════════════════════════════════════════════════════════════════
# normalize_year — 11 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeYear:
    def test_int_year_2020(self):
        assert normalize_year(2020) == 2020

    def test_float_year_2020(self):
        assert normalize_year(2020.0) == 2020

    def test_string_year_2020(self):
        assert normalize_year("2020") == 2020

    def test_string_fy2020(self):
        assert normalize_year("FY2020") == 2020

    def test_string_year_ending_march_2021(self):
        assert normalize_year("Year ending March 2021") == 2021

    def test_string_range_2020_21(self):
        assert normalize_year("2020-21") == 2020

    def test_string_no_year_here(self):
        assert normalize_year("no year here") is None

    def test_year_none(self):
        assert normalize_year(None) is None

    def test_year_nan(self):
        assert normalize_year(float("nan")) is None

    def test_year_below_1900(self):
        assert normalize_year(1899) is None

    def test_year_above_2100(self):
        assert normalize_year(2101) is None


# ══════════════════════════════════════════════════════════════════════════════
# normalize_numeric — 10 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeNumeric:
    def test_plain_number_1000(self):
        assert normalize_numeric("1000") == 1000.0

    def test_number_with_commas(self):
        assert normalize_numeric("1,000.50") == 1000.50

    def test_percentage_15_5(self):
        assert normalize_numeric("15.5%") == pytest.approx(0.155)

    def test_percentage_25(self):
        assert normalize_numeric("25%") == pytest.approx(0.25)

    def test_dash(self):
        assert normalize_numeric("-") == 0.0

    def test_none(self):
        assert normalize_numeric(None) is None

    def test_nan(self):
        assert normalize_numeric(float("nan")) is None

    def test_negative_500(self):
        assert normalize_numeric("-500") == -500.0

    def test_decimal_0_053(self):
        assert normalize_numeric("0.053") == 0.053

    def test_large_indian_format(self):
        assert normalize_numeric("10,00,000") == 1000000.0


# ══════════════════════════════════════════════════════════════════════════════
# normalize_sector_name — 3 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeSectorName:
    def test_it_to_technology(self):
        assert normalize_sector_name("it") == "Information Technology"

    def test_fmcg_to_consumer_goods(self):
        assert normalize_sector_name("FMCG") == "Consumer Goods"

    def test_pharma_with_whitespace(self):
        assert normalize_sector_name("  pharma  ") == "Pharmaceuticals"


# ══════════════════════════════════════════════════════════════════════════════
# DQValidator — 17 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDQValidator:
    def test_dq01_pk_uniqueness(self):
        df_ok = pd.DataFrame({"company_id": [1, 2, 3]})
        df_dup = pd.DataFrame({"company_id": [1, 1, 2, 3, 3, 3]})

        def _respond(sql, params=None):
            nonlocal _respond
            table = None
            for t in ["companies", "sectors", "profitandloss", "balancesheet",
                       "cashflow", "stock_prices", "analysis", "documents",
                       "financial_ratios", "peer_percentiles"]:
                if t in sql:
                    table = t
                    break
            if table == "companies":
                return df_dup
            return _empty_df()

        v = _mkv(_respond)
        failures = v.dq01_pk_uniqueness()
        assert len(failures) >= 1
        assert any("Duplicate PK" in f["message"] for f in failures)
        assert any(f["rule"] == "DQ-01" for f in failures)

    def test_dq02_composite_pk(self):
        df_dup = pd.DataFrame({
            "company_id": [1, 1, 2, 2],
            "year": [2020, 2020, 2021, 2021],
        })

        def _respond(sql, params=None):
            return df_dup

        v = _mkv([df_dup, df_dup, df_dup])
        failures = v.dq02_composite_uniqueness()
        assert len(failures) >= 2
        assert any("Duplicate" in f["message"] for f in failures)
        assert all(f["rule"] == "DQ-02" for f in failures)

    def test_dq03_fk_integrity(self):
        companies_df = pd.DataFrame({"company_id": [1, 2, 3]})
        orphan_df = pd.DataFrame({"company_id": [99]})
        empty = _empty_df()

        def _respond(sql, params=None):
            if "FROM companies" in sql:
                return companies_df
            if "profitandloss" in sql:
                return orphan_df
            return _empty_df()

        v = _mkv(_respond)
        failures = v.dq03_fk_integrity()
        assert len(failures) >= 1
        assert any("FK violation" in f["message"] for f in failures)

    def test_dq04_balance_sheet_balance(self):
        imbalanced = pd.DataFrame({
            "bs_id": [1],
            "company_id": [10],
            "year": [2022],
            "total_assets": [1000.0],
            "total_liabilities": [600.0],
            "shareholders_equity": [350.0],
        })
        v = _mkv([imbalanced])
        failures = v.dq04_bs_balance()
        assert len(failures) >= 1
        assert "BS imbalance" in failures[0]["message"]

    def test_dq05_opm_cross_check(self):
        mismatch = pd.DataFrame({
            "pnl_id": [1],
            "company_id": [10],
            "year": [2022],
            "operating_profit_margin": [0.30],
            "operating_profit": [200.0],
            "sales": [1000.0],
        })
        v = _mkv([mismatch])
        failures = v.dq05_opm_cross_check()
        assert len(failures) >= 1
        assert "OPM mismatch" in failures[0]["message"]

    def test_dq06_positive_sales(self):
        neg_sales = pd.DataFrame({
            "pnl_id": [1],
            "company_id": [10],
            "year": [2022],
            "sales": [-500.0],
        })
        v = _mkv([neg_sales])
        failures = v.dq06_positive_sales()
        assert len(failures) >= 1
        assert "Non-positive sales" in failures[0]["message"]

    def test_dq07_net_cash(self):
        neg_cash = pd.DataFrame({
            "bs_id": [1],
            "company_id": [10],
            "year": [2022],
            "cash_and_equivalents": [-100.0],
        })
        v = _mkv([neg_cash])
        failures = v.dq07_net_cash()
        assert len(failures) >= 1
        assert "Negative cash" in failures[0]["message"]

    def test_dq08_tax_rate(self):
        bad_tax = pd.DataFrame({
            "pnl_id": [1],
            "company_id": [10],
            "year": [2022],
            "tax_rate": [2.5],
        })
        v = _mkv([bad_tax])
        failures = v.dq08_tax_rate()
        assert len(failures) >= 1
        assert "Tax rate out of" in failures[0]["message"]

    def test_dq09_dividend_cap(self):
        high_div = pd.DataFrame({
            "pnl_id": [1],
            "company_id": [10],
            "year": [2022],
            "dividend_payout_pct": [3.5],
        })
        v = _mkv([high_div])
        failures = v.dq09_dividend_payout()
        assert len(failures) >= 1
        assert "200%" in failures[0]["message"]

    def test_dq10_valid_urls(self):
        bad_url = pd.DataFrame({
            "company_id": [10],
            "ticker": ["BAD"],
            "website": ["not-a-valid-url"],
        })
        v = _mkv([bad_url])
        failures = v.dq10_valid_urls()
        assert len(failures) >= 1
        assert "Invalid website URL" in failures[0]["message"]

    def test_dq11_eps_sign(self):
        sign_mismatch = pd.DataFrame({
            "pnl_id": [1],
            "company_id": [10],
            "year": [2022],
            "eps": [10.0],
            "net_profit": [-500.0],
        })
        v = _mkv([sign_mismatch])
        failures = v.dq11_eps_sign()
        assert len(failures) >= 1
        assert "EPS sign mismatch" in failures[0]["message"]

    def test_dq12_bse_balance(self):
        low_ca = pd.DataFrame({
            "bs_id": [1],
            "company_id": [10],
            "year": [2022],
            "current_assets": [100.0],
            "current_liabilities": [500.0],
        })
        v = _mkv([low_ca])
        failures = v.dq12_ca_cl_balance()
        assert len(failures) >= 1
        assert "Current assets" in failures[0]["message"]

    def test_dq13_coverage(self):
        zero_rows = pd.DataFrame({"cnt": [0]})

        def _respond(sql, params=None):
            return zero_rows

        v = _mkv(_respond)
        failures = v.dq13_coverage()
        assert len(failures) >= 1
        assert "minimum expected" in failures[0]["message"]

    def test_dq14_year_range(self):
        bad_year = pd.DataFrame({"year": [1880]})

        def _respond(sql, params=None):
            return bad_year

        v = _mkv(_respond)
        failures = v.dq14_year_range()
        assert len(failures) >= 1
        assert "outside allowed range" in failures[0]["message"]

    def test_dq15_duplicate_tickers(self):
        dup_ticker = pd.DataFrame({
            "ticker": ["RELIANCE", "TCS", "RELIANCE"],
        })
        v = _mkv([dup_ticker])
        failures = v.dq15_no_duplicate_tickers()
        assert len(failures) >= 1
        assert "Duplicate ticker" in failures[0]["message"]

    def test_dq16_market_cap(self):
        zero_mcap = pd.DataFrame({
            "company_id": [10],
            "ticker": ["ZERO"],
            "market_cap": [0.0],
        })
        v = _mkv([zero_mcap])
        failures = v.dq16_market_cap_positive()
        assert len(failures) >= 1
        assert "Non-positive market cap" in failures[0]["message"]

    def test_export_failures(self):
        failures = [
            {
                "table": "companies",
                "company_id": 1,
                "year": 2022,
                "rule": "DQ-01",
                "severity": "CRITICAL",
                "message": "Duplicate PK",
            },
        ]
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            v.export_failures(failures, tmp_path)
            assert os.path.exists(tmp_path)
            df = pd.read_csv(tmp_path)
            assert "rule" in df.columns
            assert "severity" in df.columns
            assert "message" in df.columns
            assert len(df) == 1
        finally:
            os.unlink(tmp_path)
