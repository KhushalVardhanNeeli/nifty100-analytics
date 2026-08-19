"""One test per DQ rule — each crafts a DataFrame that violates exactly that rule."""

import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.etl.validator import DQValidator


def _mk(query_results):
    v = DQValidator.__new__(DQValidator)
    v.engine = MagicMock()
    v._query = MagicMock(
        side_effect=(list(query_results) if not callable(query_results) else query_results)
    )
    return v


def _empty():
    return pd.DataFrame()


class TestDQRules:
    def test_dq01_pk_uniqueness(self):
        v = _mk(
            lambda sql, params=None: (
                pd.DataFrame({"pk": [1, 1]}) if "companies" in sql else _empty()
            )
        )
        f = v.dq01_pk_uniqueness()
        assert any(x["rule"] == "DQ-01" and x["severity"] == "CRITICAL" for x in f)

    def test_dq02_composite_uniqueness(self):
        dup = pd.DataFrame({"company_id": [1, 1], "year": [2020, 2020]})
        v = _mk(lambda sql, params=None: dup if "profitandloss" in sql else _empty())
        f = v.dq02_composite_uniqueness()
        assert any(x["rule"] == "DQ-02" and x["severity"] == "CRITICAL" for x in f)

    def test_dq03_fk_integrity(self):
        def r(sql, params=None):
            if "FROM companies" in sql:
                return pd.DataFrame({"company_id": [1]})
            if "profitandloss" in sql:
                return pd.DataFrame({"company_id": [99]})
            return _empty()

        f = _mk(r).dq03_fk_integrity()
        assert any(x["rule"] == "DQ-03" and x["severity"] == "CRITICAL" for x in f)

    def test_dq04_bs_balance(self):
        df = pd.DataFrame(
            {
                "bs_id": [1],
                "company_id": [1],
                "year": [2020],
                "total_assets": [1000.0],
                "total_liabilities": [500.0],
            }
        )
        f = _mk([df]).dq04_bs_balance()
        assert any(x["rule"] == "DQ-04" for x in f)

    def test_dq05_opm_cross_check(self):
        df = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [1],
                "year": [2020],
                "opm_percentage": [50.0],
                "operating_profit": [100.0],
                "sales": [1000.0],
            }
        )
        f = _mk([df]).dq05_opm_cross_check()
        assert any(x["rule"] == "DQ-05" for x in f)

    def test_dq06_positive_sales(self):
        df = pd.DataFrame({"pnl_id": [1], "company_id": [1], "year": [2020], "sales": [-5.0]})
        f = _mk([df]).dq06_positive_sales()
        assert any(x["rule"] == "DQ-06" for x in f)

    def test_dq07_net_cash(self):
        df = pd.DataFrame(
            {
                "cf_id": [1],
                "company_id": [1],
                "year": [2020],
                "operating_activity": [100.0],
                "investing_activity": [0.0],
                "financing_activity": [0.0],
                "net_cash_flow": [None],
            }
        )
        f = _mk([df]).dq07_net_cash()
        assert any(x["rule"] == "DQ-07" for x in f)

    def test_dq08_tax_rate(self):
        df = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [1],
                "year": [2020],
                "tax_percentage": [150.0],
            }
        )
        f = _mk([df]).dq08_tax_rate()
        assert any(x["rule"] == "DQ-08" for x in f)

    def test_dq09_dividend_cap(self):
        df = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [1],
                "year": [2020],
                "dividend_payout": [300.0],
            }
        )
        f = _mk([df]).dq09_dividend_cap()
        assert any(x["rule"] == "DQ-09" for x in f)

    def test_dq10_valid_urls(self):
        df = pd.DataFrame({"company_id": [1], "ticker": ["X"], "website": ["not a url"]})
        f = _mk([df]).dq10_valid_urls()
        assert any(x["rule"] == "DQ-10" for x in f)

    def test_dq11_eps_sign(self):
        df = pd.DataFrame(
            {
                "pnl_id": [1],
                "company_id": [1],
                "year": [2020],
                "eps": [10.0],
                "net_profit": [-5.0],
            }
        )
        f = _mk([df]).dq11_eps_sign()
        assert any(x["rule"] == "DQ-11" for x in f)

    def test_dq12_bs_equity_balance(self):
        df = pd.DataFrame(
            {
                "bs_id": [1],
                "company_id": [1],
                "year": [2020],
                "equity_capital": [100.0],
                "reserves": [0.0],
                "borrowings": [0.0],
                "other_liabilities": [0.0],
                "total_liabilities": [1000.0],
            }
        )
        f = _mk([df]).dq12_bs_equity_balance()
        assert any(x["rule"] == "DQ-12" for x in f)

    def test_dq13_coverage(self):
        f = _mk(lambda sql, params=None: pd.DataFrame({"cnt": [0]})).dq13_coverage()
        assert any(x["rule"] == "DQ-13" for x in f)

    def test_dq14_year_range(self):
        f = _mk(lambda sql, params=None: pd.DataFrame({"year": [1880]})).dq14_year_range()
        assert any(x["rule"] == "DQ-14" for x in f)
