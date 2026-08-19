import os
import sys
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.etl.loader import ETLPipeline, _f


def _mkpipeline():
    p = ETLPipeline.__new__(ETLPipeline)
    p.data_dir = MagicMock()
    p.data_dir / "raw" / "profitandloss.xlsx"
    p.db_path = None
    p.engine = MagicMock()
    p._ticker_to_id = {"TCS": 1, "RELIANCE": 2}
    p.counts = {}
    return p


class TestLoader:
    def test_float_conversion(self):
        assert _f("100.5") == 100.5
        assert _f(None) is None
        assert _f(float("nan")) is None

    def test_negative_float(self):
        assert _f("-500") == -500.0

    def test_ticker_resolve(self):
        p = _mkpipeline()
        assert p._resolve("tcs") == 1
        assert p._resolve("reliance.") == 2
        assert p._resolve("UNKNOWN") is None
        assert p._resolve(None) is None

    def test_ticker_map_normalized(self):
        p = _mkpipeline()
        p._ticker_to_id = {}
        df = pd.DataFrame({"company_id": [1, 2], "ticker": [" tcs ", "RELIANCE"]})
        with patch("pandas.read_sql", return_value=df):
            m = p._ticker_map()
        assert m["TCS"] == 1 and m["RELIANCE"] == 2

    def test_load_excel_lowercases_columns(self):
        p = _mkpipeline()
        df = pd.DataFrame({"Company ID": [1], "Net Profit": [10]})
        with patch("pandas.read_excel", return_value=df):
            out = p._load_excel(MagicMock(), header_row=0)
        assert "company_id" in out.columns and "net_profit" in out.columns

    def test_counts_recorded(self):
        p = _mkpipeline()
        p.counts["companies"] = {"loaded": 92, "rejected": 0}
        assert p.counts["companies"]["loaded"] == 92

    def test_extra_tickers_discovery(self):
        p = _mkpipeline()
        p._ticker_to_id = {"TCS": 1}
        df = pd.DataFrame({"company_id": ["TCS", "WIPRO", "tcs"]})
        with patch.object(p, "_load_excel", return_value=df):
            extra = p._extra_tickers()
        assert extra == {"WIPRO"}

    def test_load_financial_skip_bad_year(self):
        p = _mkpipeline()
        p._resolve = MagicMock(side_effect=[1, 1])
        p.counts = {}
        df = pd.DataFrame(
            {"company_id": ["TCS", "TCS"], "year": ["2020", "TTM"], "sales": [100, 200]}
        )
        mapper = lambda row, cid, year: {"company_id": cid, "year": year}
        with patch.object(p, "_load_excel", return_value=df), patch("pandas.DataFrame.to_sql"):
            p._load_financial("profitandloss", "profitandloss", mapper)
        assert p.counts["profitandloss"]["rejected"] == 1

    def test_drop_duplicates(self):
        df = pd.DataFrame({"company_id": [1, 1], "year": [2020, 2020]})
        out = df.drop_duplicates(subset=["company_id", "year"])
        assert len(out) == 1
