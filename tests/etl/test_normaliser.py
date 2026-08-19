import os
import sys
import tempfile
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.etl.normaliser import (
    normalize_numeric,
    normalize_sector_name,
    normalize_ticker,
    normalize_year,
)
from src.etl.validator import DQValidator

# ── Helper ────────────────────────────────────────────────────────────────────


def _mkv(query_results):
    v = DQValidator.__new__(DQValidator)
    v.engine = MagicMock()
    v._query = MagicMock(
        side_effect=(list(query_results) if not callable(query_results) else query_results)
    )
    return v


def _empty_df():
    return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# normalize_ticker — 15 tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeTicker:
    def test_lowercase_upper(self):
        assert normalize_ticker("reliance") == "RELIANCE"

    def test_whitespace(self):
        assert normalize_ticker("  tcs  ") == "TCS"

    def test_leading_dot(self):
        assert normalize_ticker(".INFY") == "INFY"

    def test_trailing_dot(self):
        assert normalize_ticker("TCS.") == "TCS"

    def test_none(self):
        assert normalize_ticker(None) is None

    def test_nan(self):
        assert normalize_ticker(float("nan")) is None

    def test_empty_string(self):
        assert normalize_ticker("") is None

    def test_int(self):
        assert normalize_ticker(123) == "123"

    def test_ampersand(self):
        assert normalize_ticker("m&m") == "M&M"

    def test_hyphen(self):
        assert normalize_ticker("bajaj-auto") == "BAJAJ-AUTO"

    def test_internal_space(self):
        assert normalize_ticker("HDFC Bank") == "HDFC BANK"

    def test_bool(self):
        assert normalize_ticker(True) is None

    def test_only_dots(self):
        assert normalize_ticker("...") is None

    def test_nse_suffix(self):
        assert normalize_ticker("tcs.NS") == "TCS.NS"

    def test_whitespace_tabs(self):
        assert normalize_ticker("\ttcs\n") == "TCS"


# ══════════════════════════════════════════════════════════════════════════════
# normalize_year — 21 tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeYear:
    def test_int_2020(self):
        assert normalize_year(2020) == 2020

    def test_float_2020(self):
        assert normalize_year(2020.0) == 2020

    def test_string_2020(self):
        assert normalize_year("2020") == 2020

    def test_fy2020(self):
        assert normalize_year("FY2020") == 2020

    def test_fy_space_2020(self):
        assert normalize_year("FY 2020") == 2020

    def test_fy_two_digit(self):
        assert normalize_year("FY20") == 2020

    def test_year_ending_march(self):
        assert normalize_year("Year ending March 2021") == 2021

    def test_range(self):
        assert normalize_year("2020-21") == 2020

    def test_dec_2012(self):
        assert normalize_year("Dec 2012") == 2012

    def test_mar_2014(self):
        assert normalize_year("Mar 2014") == 2014

    def test_two_digit_mar13(self):
        assert normalize_year("Mar-13") == 2013

    def test_two_digit_mar24(self):
        assert normalize_year("Mar-24") == 2024

    def test_two_digit_space(self):
        assert normalize_year("Mar 24") == 2024

    def test_ttm(self):
        assert normalize_year("TTM") is None

    def test_bare_two_digit(self):
        assert normalize_year("24") == 2024

    def test_no_year(self):
        assert normalize_year("no year here") is None

    def test_none(self):
        assert normalize_year(None) is None

    def test_nan(self):
        assert normalize_year(float("nan")) is None

    def test_below_1900(self):
        assert normalize_year(1899) is None

    def test_above_2100(self):
        assert normalize_year(2101) is None

    def test_empty(self):
        assert normalize_year("") is None


# ══════════════════════════════════════════════════════════════════════════════
# normalize_numeric — 10 tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeNumeric:
    def test_plain(self):
        assert normalize_numeric("1000") == 1000.0

    def test_commas(self):
        assert normalize_numeric("1,000.50") == 1000.50

    def test_pct_15_5(self):
        assert normalize_numeric("15.5%") == pytest.approx(0.155)

    def test_pct_25(self):
        assert normalize_numeric("25%") == pytest.approx(0.25)

    def test_dash(self):
        assert normalize_numeric("-") == 0.0

    def test_none(self):
        assert normalize_numeric(None) is None

    def test_nan(self):
        assert normalize_numeric(float("nan")) is None

    def test_negative(self):
        assert normalize_numeric("-500") == -500.0

    def test_decimal(self):
        assert normalize_numeric("0.053") == 0.053

    def test_indian_format(self):
        assert normalize_numeric("10,00,000") == 1000000.0


# ══════════════════════════════════════════════════════════════════════════════
# normalize_sector_name — 3 tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeSectorName:
    def test_it(self):
        assert normalize_sector_name("it") == "Information Technology"

    def test_fmcg(self):
        assert normalize_sector_name("FMCG") == "Consumer Goods"

    def test_pharma(self):
        assert normalize_sector_name("  pharma  ") == "Pharmaceuticals"


# ══════════════════════════════════════════════════════════════════════════════
# DQValidator — 17 tests (16 rules + export)
# ══════════════════════════════════════════════════════════════════════════════


class TestDQValidator:
    def test_dq01_pk_uniqueness(self):
        dup = pd.DataFrame({"pk": [1, 1, 2, 3, 3, 3]})

        def _respond(sql, params=None):
            return dup if "companies" in sql else _empty_df()

        v = _mkv(_respond)
        failures = v.dq01_pk_uniqueness()
        assert failures
        assert all(f["rule"] == "DQ-01" for f in failures)
        assert all(f["severity"] == "CRITICAL" for f in failures)
        assert any("Duplicate PK" in f["issue"] for f in failures)

    def test_dq02_composite_pk(self):
        dup = pd.DataFrame({"company_id": [1, 1, 2], "year": [2020, 2020, 2021]})

        def _respond(sql, params=None):
            return dup if "profitandloss" in sql else _empty_df()

        v = _mkv(_respond)
        failures = v.dq02_composite_uniqueness()
        assert failures
        assert all(f["rule"] == "DQ-02" for f in failures)
        assert all(f["severity"] == "CRITICAL" for f in failures)

    def test_dq03_fk_integrity(self):
        companies = pd.DataFrame({"company_id": [1, 2, 3]})
        orphan = pd.DataFrame({"company_id": [99]})

        def _respond(sql, params=None):
            if "FROM companies" in sql:
                return companies
            if "profitandloss" in sql:
                return orphan
            return _empty_df()

        v = _mkv(_respond)
        failures = v.dq03_fk_integrity()
        assert failures
        assert all(f["rule"] == "DQ-03" for f in failures)
        assert all(f["severity"] == "CRITICAL" for f in failures)
        assert any("FK violation" in f["issue"] for f in failures)

    def test_dq04_bs_balance(self):
        imbalanced = pd.DataFrame(
            {
                "bs_id": [1],
                "company_id": [10],
                "year": [2022],
                "total_assets": [1000.0],
                "total_liabilities": [600.0],
            }
        )
        v = _mkv([imbalanced])
        failures = v.dq04_bs_balance()
        assert failures
        assert all(f["severity"] == "WARNING" for f in failures)
        assert "BS imbalance" in failures[0]["issue"]

    def test_dq05_opm_cross_check(self):
        mismatch = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [10],
                "year": [2022],
                "opm_percentage": [13.53],
                "operating_profit": [305.8],
                "sales": [1000.0],
            }
        )
        v = _mkv([mismatch])
        failures = v.dq05_opm_cross_check()
        assert failures
        assert all(f["severity"] == "WARNING" for f in failures)
        assert "OPM mismatch" in failures[0]["issue"]

    def test_dq06_positive_sales(self):
        neg = pd.DataFrame({"pnl_id": [1], "company_id": [10], "year": [2022], "sales": [-500.0]})
        v = _mkv([neg])
        failures = v.dq06_positive_sales()
        assert failures
        assert "Non-positive sales" in failures[0]["issue"]

    def test_dq07_net_cash(self):
        missing = pd.DataFrame(
            {
                "cf_id": [1],
                "company_id": [10],
                "year": [2022],
                "operating_activity": [100.0],
                "investing_activity": [-50.0],
                "financing_activity": [-20.0],
                "net_cash_flow": [None],
            }
        )
        v = _mkv([missing])
        failures = v.dq07_net_cash()
        assert failures
        assert "net_cash_flow missing" in failures[0]["issue"]

    def test_dq08_tax_rate(self):
        bad = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [10],
                "year": [2022],
                "tax_percentage": [250.0],
            }
        )
        v = _mkv([bad])
        failures = v.dq08_tax_rate()
        assert failures
        assert "Tax rate out of" in failures[0]["issue"]

    def test_dq09_dividend_cap(self):
        high = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [10],
                "year": [2022],
                "dividend_payout": [350.0],
            }
        )
        v = _mkv([high])
        failures = v.dq09_dividend_cap()
        assert failures
        assert "200%" in failures[0]["issue"]

    def test_dq10_valid_urls(self):
        bad = pd.DataFrame({"company_id": [10], "ticker": ["BAD"], "website": ["not-a-valid-url"]})
        v = _mkv([bad])
        failures = v.dq10_valid_urls()
        assert failures
        assert "Invalid website URL" in failures[0]["issue"]

    def test_dq11_eps_sign(self):
        bad = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [10],
                "year": [2022],
                "eps": [10.0],
                "net_profit": [-500.0],
            }
        )
        v = _mkv([bad])
        failures = v.dq11_eps_sign()
        assert failures
        assert "EPS sign mismatch" in failures[0]["issue"]

    def test_dq12_bs_equity_balance(self):
        bad = pd.DataFrame(
            {
                "bs_id": [1],
                "company_id": [10],
                "year": [2022],
                "equity_capital": [100.0],
                "reserves": [50.0],
                "borrowings": [20.0],
                "other_liabilities": [10.0],
                "total_liabilities": [1000.0],
            }
        )
        v = _mkv([bad])
        failures = v.dq12_bs_equity_balance()
        assert failures
        assert "reconcile" in failures[0]["issue"]

    def test_dq13_coverage(self):
        zero = pd.DataFrame({"cnt": [0]})

        def _respond(sql, params=None):
            return zero

        v = _mkv(_respond)
        failures = v.dq13_coverage()
        assert failures
        assert "minimum expected" in failures[0]["issue"]

    def test_dq14_year_range(self):
        bad = pd.DataFrame({"year": [1880]})

        def _respond(sql, params=None):
            return bad

        v = _mkv(_respond)
        failures = v.dq14_year_range()
        assert failures
        assert "outside allowed range" in failures[0]["issue"]

    def test_dq15_duplicate_tickers(self):
        dup = pd.DataFrame({"ticker": ["RELIANCE", "TCS", "RELIANCE"]})
        v = _mkv([dup])
        failures = v.dq15_no_duplicate_tickers()
        assert failures
        assert "Duplicate ticker" in failures[0]["issue"]

    def test_dq16_market_cap(self):
        zero = pd.DataFrame({"company_id": [10], "ticker": ["ZERO"], "market_cap_crore": [0.0]})
        v = _mkv([zero])
        failures = v.dq16_market_cap_positive()
        assert failures
        assert "Non-positive market cap" in failures[0]["issue"]

    def test_export_failures(self):
        failures = [
            {
                "rule": "DQ-01",
                "severity": "CRITICAL",
                "table": "companies",
                "field": "company_id",
                "company_id": 1,
                "year": 2022,
                "issue": "Duplicate PK",
            }
        ]
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            v.export_failures(failures, tmp_path)
            assert os.path.exists(tmp_path)
            df = pd.read_csv(tmp_path)
            assert "company_id" in df.columns
            assert "field" in df.columns
            assert "issue" in df.columns
            assert "severity" in df.columns
            assert len(df) == 1
        finally:
            os.unlink(tmp_path)
