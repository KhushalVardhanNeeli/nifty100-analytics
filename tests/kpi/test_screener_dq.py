import os
import sys
import tempfile
import time
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analytics.peer import PeerAnalyzer
from src.etl.validator import DQValidator
from src.screener.engine import ScreenerEngine


def _empty_df():
    return pd.DataFrame()


def _mkv(query_results):
    v = DQValidator.__new__(DQValidator)
    v.engine = MagicMock()
    if callable(query_results):
        v._query = MagicMock(side_effect=query_results)
    else:
        v._query = MagicMock(side_effect=list(query_results))
    return v


# ══════════════════════════════════════════════════════════════════════════════
# 6 Validator Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestValidatorIntegration:
    def test_full_validation_run(self):
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()
        v._query = MagicMock()

        v.dq01_pk_uniqueness = MagicMock(
            return_value=[
                {
                    "table": "companies",
                    "company_id": 1,
                    "year": None,
                    "rule": "DQ-01",
                    "severity": "CRITICAL",
                    "message": "Duplicate PK",
                }
            ]
        )
        v.dq02_composite_uniqueness = MagicMock(return_value=[])
        v.dq03_fk_integrity = MagicMock(
            return_value=[
                {
                    "table": "profitandloss",
                    "company_id": 99,
                    "year": None,
                    "rule": "DQ-03",
                    "severity": "CRITICAL",
                    "message": "FK violation",
                }
            ]
        )
        v.dq04_bs_balance = MagicMock(return_value=[])
        v.dq05_opm_cross_check = MagicMock(return_value=[])
        v.dq06_positive_sales = MagicMock(return_value=[])
        v.dq07_net_cash = MagicMock(
            return_value=[
                {
                    "table": "balancesheet",
                    "company_id": 5,
                    "year": 2022,
                    "rule": "DQ-07",
                    "severity": "WARNING",
                    "message": "Negative cash",
                }
            ]
        )
        v.dq08_tax_rate = MagicMock(return_value=[])
        v.dq09_dividend_cap = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_bs_equity_balance = MagicMock(return_value=[])
        v.dq13_coverage = MagicMock(return_value=[])
        v.dq14_year_range = MagicMock(return_value=[])
        v.dq15_no_duplicate_tickers = MagicMock(return_value=[])
        v.dq16_market_cap_positive = MagicMock(return_value=[])

        failures = v.run_all()
        assert len(failures) == 3
        rules = {f["rule"] for f in failures}
        assert "DQ-01" in rules
        assert "DQ-03" in rules
        assert "DQ-07" in rules

    def test_critical_vs_warning_severity(self):
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()
        v._query = MagicMock()

        v.dq01_pk_uniqueness = MagicMock(
            return_value=[
                {
                    "table": "companies",
                    "company_id": None,
                    "year": None,
                    "rule": "DQ-01",
                    "severity": "CRITICAL",
                    "message": "Duplicate PK",
                }
            ]
        )
        v.dq02_composite_uniqueness = MagicMock(return_value=[])
        v.dq03_fk_integrity = MagicMock(return_value=[])
        v.dq04_bs_balance = MagicMock(return_value=[])
        v.dq05_opm_cross_check = MagicMock(return_value=[])
        v.dq06_positive_sales = MagicMock(return_value=[])
        v.dq07_net_cash = MagicMock(
            return_value=[
                {
                    "table": "balancesheet",
                    "company_id": 1,
                    "year": 2022,
                    "rule": "DQ-07",
                    "severity": "WARNING",
                    "message": "Negative cash",
                }
            ]
        )
        v.dq08_tax_rate = MagicMock(return_value=[])
        v.dq09_dividend_cap = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_bs_equity_balance = MagicMock(return_value=[])
        v.dq13_coverage = MagicMock(return_value=[])
        v.dq14_year_range = MagicMock(return_value=[])
        v.dq15_no_duplicate_tickers = MagicMock(return_value=[])
        v.dq16_market_cap_positive = MagicMock(return_value=[])

        failures = v.run_all()
        assert len(failures) == 2
        severities = {f["severity"] for f in failures}
        assert "CRITICAL" in severities
        assert "WARNING" in severities

    def test_empty_dataset(self):
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()
        v._query = MagicMock()

        v.dq01_pk_uniqueness = MagicMock(return_value=[])
        v.dq02_composite_uniqueness = MagicMock(return_value=[])
        v.dq03_fk_integrity = MagicMock(return_value=[])
        v.dq04_bs_balance = MagicMock(return_value=[])
        v.dq05_opm_cross_check = MagicMock(return_value=[])
        v.dq06_positive_sales = MagicMock(return_value=[])
        v.dq07_net_cash = MagicMock(return_value=[])
        v.dq08_tax_rate = MagicMock(return_value=[])
        v.dq09_dividend_cap = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_bs_equity_balance = MagicMock(return_value=[])
        v.dq13_coverage = MagicMock(return_value=[])
        v.dq14_year_range = MagicMock(return_value=[])
        v.dq15_no_duplicate_tickers = MagicMock(return_value=[])
        v.dq16_market_cap_positive = MagicMock(return_value=[])

        failures = v.run_all()
        assert len(failures) == 0

    def test_mixed_data(self):
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()

        dup_df = pd.DataFrame({"pk": [1, 1, 2]})

        def _respond(sql, params=None):
            return dup_df

        v._query = MagicMock(side_effect=_respond)
        v.dq01_pk_uniqueness()
        failures = [f for f in v.dq01_pk_uniqueness()]
        assert failures

        clean_companies = pd.DataFrame({"pk": [1, 2, 3]})
        clean_empty = pd.DataFrame()

        def _respond_clean(sql, params=None):
            if 'FROM "companies"' in sql:
                return clean_companies
            return clean_empty

        v._query = MagicMock(side_effect=_respond_clean)
        failures = v.dq01_pk_uniqueness()
        assert len(failures) == 0

    def test_large_dataset_performance(self):
        n = 10000
        large_df = pd.DataFrame(
            {
                "pnl_id": range(1, n + 1),
                "company_id": np.random.randint(1, 101, n),
                "year": np.random.randint(2015, 2023, n),
                "sales": np.random.uniform(100, 1000000, n),
            }
        )

        v = _mkv([large_df])
        start = time.time()
        v.dq06_positive_sales()
        elapsed = time.time() - start
        assert elapsed < 2.0

    def test_failure_export_format(self):
        failures = [
            {
                "company_id": 1,
                "field": "company_id",
                "issue": "Duplicate PK",
                "severity": "CRITICAL",
                "rule": "DQ-01",
                "year": 2022,
                "table": "companies",
            },
            {
                "company_id": 2,
                "field": "sales",
                "issue": "Non-positive sales: -500",
                "severity": "CRITICAL",
                "rule": "DQ-06",
                "year": 2021,
                "table": "profitandloss",
            },
        ]

        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            v.export_failures(failures, tmp_path)
            assert os.path.exists(tmp_path)
            exported = pd.read_csv(tmp_path)
            required_cols = ["company_id", "field", "issue", "severity"]
            for col in required_cols:
                assert col in exported.columns
            assert len(exported) == 2
            assert exported.iloc[0]["rule"] == "DQ-01"
            assert exported.iloc[0]["severity"] == "CRITICAL"
        finally:
            os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════════════════
# 3 Peer Metrics Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPeerMetrics:
    def test_percent_rank_calculation(self):
        series = pd.Series([10.0, 20.0, 30.0, 40.0])
        n = len(series)
        ranks = series.rank(method="min") - 1
        pct = (ranks / (n - 1)) * 100

        assert pct.iloc[0] == pytest.approx(0.0)
        assert pct.iloc[1] == pytest.approx(100.0 / 3.0)
        assert pct.iloc[2] == pytest.approx(200.0 / 3.0)
        assert pct.iloc[3] == pytest.approx(100.0)

    def test_de_inverted(self):
        series = pd.Series([0.5, 1.0, 2.0, 3.0])
        n = len(series)
        ranks = series.rank(method="min") - 1
        pct = (ranks / (n - 1)) * 100
        inverted = 100 - pct

        assert inverted.iloc[0] == pytest.approx(100.0)
        assert inverted.iloc[-1] == pytest.approx(0.0)

    def test_peer_metrics_list(self):
        names = [m[0] for m in PeerAnalyzer.METRICS]
        assert len(names) == 10
        for required in [
            "roe",
            "roce",
            "net_profit_margin",
            "debt_to_equity",
            "fcf",
            "pat_cagr_5y",
            "revenue_cagr_5y",
            "eps_cagr_5y",
            "interest_coverage",
            "asset_turnover",
        ]:
            assert required in names


# ══════════════════════════════════════════════════════════════════════════════
# 6 Screener Config Tests
# ══════════════════════════════════════════════════════════════════════════════


def _engine():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
    )
    return ScreenerEngine(config_path=config_path, db_path=":memory:")


class TestScreenerConfig:
    def test_load_yaml_config(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        assert "presets" in config
        assert len(config["presets"]) == 6
        expected = [
            "Quality_Compounder",
            "Value_Pick",
            "Growth_Accelerator",
            "Dividend_Champion",
            "Debt_Free_Blue_Chip",
            "Turnaround_Watch",
        ]
        for preset_name in expected:
            assert preset_name in config["presets"]

    def test_filter_application(self):
        engine = _engine()
        df = pd.DataFrame(
            {
                "company_id": [1, 2, 3],
                "roe": [20.0, 8.0, 18.0],
                "debt_to_equity": [1.0, 2.5, 0.5],
                "free_cash_flow": [100.0, 50.0, 200.0],
                "revenue_cagr_5y": [12.0, 5.0, 15.0],
                "broad_sector": [
                    "Information Technology",
                    "Automotive",
                    "Consumer Staples",
                ],
            }
        )
        filtered = engine.apply_filters(df.copy(), "Quality_Compounder")
        assert len(filtered) >= 1
        assert all(filtered["roe"] >= 15.0)

    def test_financial_sector_exclusion(self):
        engine = _engine()
        df = pd.DataFrame(
            {
                "company_id": [1, 2],
                "roe": [18.0, 18.0],
                "debt_to_equity": [5.0, 5.0],
                "free_cash_flow": [100.0, 100.0],
                "revenue_cagr_5y": [12.0, 12.0],
                "broad_sector": ["Information Technology", "Financials"],
            }
        )
        filtered = engine.apply_filters(df.copy(), "Quality_Compounder")
        assert len(filtered) == 1
        assert filtered.iloc[0]["broad_sector"] == "Financials"

    def test_debt_free_icr(self):
        engine = _engine()
        engine.presets = {"_test": {"filters": [{"metric": "interest_coverage", "min": 2.0}]}}
        df = pd.DataFrame(
            {
                "company_id": [1, 2],
                "interest_coverage": [None, 1.0],
                "icr_label": ["Debt Free", None],
            }
        )
        filtered = engine.apply_filters(df.copy(), "_test")
        assert len(filtered) == 1

    def test_composite_score_range(self):
        engine = _engine()
        np.random.seed(42)
        n = 50
        df = pd.DataFrame(
            {
                "company_id": range(1, n + 1),
                "roe": np.random.uniform(5, 30, n),
                "roce": np.random.uniform(5, 35, n),
                "net_profit_margin": np.random.uniform(2, 25, n),
                "debt_to_equity": np.random.uniform(0, 3, n),
                "interest_coverage": np.random.uniform(0.5, 20, n),
                "free_cash_flow": np.random.uniform(-100, 500, n),
                "fcf_cagr_5y": np.random.uniform(-10, 30, n),
                "cfo_quality_score": np.random.uniform(0.1, 2.0, n),
                "revenue_cagr_5y": np.random.uniform(-5, 25, n),
                "pat_cagr_5y": np.random.uniform(-10, 30, n),
                "broad_sector": np.random.choice(["IT", "Financials", "Auto"], n),
            }
        )
        scored = engine.composite_score(df.copy())
        assert "composite_score" in scored.columns
        valid = scored["composite_score"].dropna()
        assert valid.min() >= 0.0
        assert valid.max() <= 100.0

    def test_preset_has_required_keys(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        for preset_name, preset in config["presets"].items():
            for key in ["label", "filters", "sort_by"]:
                assert key in preset, f"Preset '{preset_name}' missing key: {key}"
            assert isinstance(preset["filters"], list)
            assert len(preset["filters"]) > 0
