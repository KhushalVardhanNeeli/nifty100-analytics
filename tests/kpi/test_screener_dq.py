import os
import sys
import tempfile
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.etl.validator import DQValidator
from src.analytics.peer import PeerAnalyzer
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

        v.dq01_pk_uniqueness = MagicMock(return_value=[
            {"table": "companies", "company_id": 1, "year": None,
             "rule": "DQ-01", "severity": "CRITICAL",
             "message": "Duplicate PK"}
        ])
        v.dq02_composite_uniqueness = MagicMock(return_value=[])
        v.dq03_fk_integrity = MagicMock(return_value=[
            {"table": "profitandloss", "company_id": 99, "year": None,
             "rule": "DQ-03", "severity": "CRITICAL",
             "message": "FK violation"}
        ])
        v.dq04_bs_balance = MagicMock(return_value=[])
        v.dq05_opm_cross_check = MagicMock(return_value=[])
        v.dq06_positive_sales = MagicMock(return_value=[])
        v.dq07_net_cash = MagicMock(return_value=[
            {"table": "balancesheet", "company_id": 5, "year": 2022,
             "rule": "DQ-07", "severity": "WARNING",
             "message": "Negative cash"}
        ])
        v.dq08_tax_rate = MagicMock(return_value=[])
        v.dq09_dividend_payout = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_ca_cl_balance = MagicMock(return_value=[])
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

        v.dq01_pk_uniqueness = MagicMock(return_value=[
            {"table": "companies", "company_id": None, "year": None,
             "rule": "DQ-01", "severity": "CRITICAL",
             "message": "Duplicate PK"}
        ])
        v.dq02_composite_uniqueness = MagicMock(return_value=[])
        v.dq03_fk_integrity = MagicMock(return_value=[])
        v.dq04_bs_balance = MagicMock(return_value=[])
        v.dq05_opm_cross_check = MagicMock(return_value=[])
        v.dq06_positive_sales = MagicMock(return_value=[])
        v.dq07_net_cash = MagicMock(return_value=[
            {"table": "balancesheet", "company_id": 1, "year": 2022,
             "rule": "DQ-07", "severity": "WARNING",
             "message": "Negative cash"}
        ])
        v.dq08_tax_rate = MagicMock(return_value=[])
        v.dq09_dividend_payout = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_ca_cl_balance = MagicMock(return_value=[])
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
        v.dq09_dividend_payout = MagicMock(return_value=[])
        v.dq10_valid_urls = MagicMock(return_value=[])
        v.dq11_eps_sign = MagicMock(return_value=[])
        v.dq12_ca_cl_balance = MagicMock(return_value=[])
        v.dq13_coverage = MagicMock(return_value=[])
        v.dq14_year_range = MagicMock(return_value=[])
        v.dq15_no_duplicate_tickers = MagicMock(return_value=[])
        v.dq16_market_cap_positive = MagicMock(return_value=[])

        failures = v.run_all()
        assert len(failures) == 0

    def test_mixed_data(self):
        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()

        dup_df = pd.DataFrame({"company_id": [1, 1, 2]})

        def _respond(sql, params=None):
            return dup_df

        v._query = MagicMock(side_effect=_respond)
        failures = v.dq01_pk_uniqueness()
        assert len(failures) >= 1

        clean_companies = pd.DataFrame({"company_id": [1, 2, 3]})
        clean_empty = pd.DataFrame()

        def _respond_clean(sql, params=None):
            if "FROM \"companies\"" in sql:
                return clean_companies
            return clean_empty

        v._query = MagicMock(side_effect=_respond_clean)
        failures = v.dq01_pk_uniqueness()
        assert len(failures) == 0

    def test_large_dataset_performance(self):
        n = 10000
        large_df = pd.DataFrame({
            "pnl_id": range(1, n + 1),
            "company_id": np.random.randint(1, 101, n),
            "year": np.random.randint(2015, 2023, n),
            "sales": np.random.uniform(100, 1000000, n),
        })

        v = _mkv([large_df])
        start = time.time()
        failures = v.dq06_positive_sales()
        elapsed = time.time() - start
        assert elapsed < 2.0

    def test_failure_export_format(self):
        failures = [
            {"table": "companies", "company_id": 1, "year": 2022,
             "rule": "DQ-01", "severity": "CRITICAL", "message": "Duplicate PK"},
            {"table": "profitandloss", "company_id": 2, "year": 2021,
             "rule": "DQ-06", "severity": "CRITICAL",
             "message": "Non-positive sales: -500"},
        ]

        v = DQValidator.__new__(DQValidator)
        v.engine = MagicMock()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            v.export_failures(failures, tmp_path)
            assert os.path.exists(tmp_path)
            exported = pd.read_csv(tmp_path)
            required_cols = ["table", "company_id", "year", "rule", "severity", "message"]
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

    def test_peer_group_assignment(self):
        companies_df = pd.DataFrame({
            "company_id": [1, 2, 3, 4, 5],
            "sector_name": ["Information Technology", "Information Technology",
                            "Automotive", "Automotive", "Pharmaceuticals"],
            "market_cap": [1000.0, 2000.0, 500.0, 600.0, 300.0],
        })

        analyzer = PeerAnalyzer(db_path=":memory:")
        mock_conn = MagicMock()
        with patch.object(analyzer, "_get_conn", return_value=mock_conn), \
             patch.object(pd, "read_sql", return_value=companies_df):
            result = analyzer._define_peer_groups()

        assert "peer_group" in result.columns
        assert result.loc[0, "peer_group"] == "Information Technology"
        assert result.loc[2, "peer_group"] == "Automotive"
        assert result.loc[4, "peer_group"] == "Pharmaceuticals"


# ══════════════════════════════════════════════════════════════════════════════
# 6 Screener Config Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestScreenerConfig:
    def test_load_yaml_config(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        assert "presets" in config
        assert len(config["presets"]) == 6
        expected_presets = [
            "Quality_Compounder", "Value_Pick", "Growth_Accelerator",
            "Dividend_Champion", "Debt_Free_Blue_Chip", "Turnaround_Watch",
        ]
        for preset_name in expected_presets:
            assert preset_name in config["presets"]

    def test_filter_application(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        engine = ScreenerEngine(config_path=config_path, db_path=":memory:")

        df = pd.DataFrame({
            "company_id": [1, 2, 3],
            "roe": [20.0, 8.0, 18.0],
            "revenue_cagr_3y": [12.0, 5.0, 15.0],
            "cfo_quality": ["High Quality", "Moderate", "High Quality"],
            "debt_to_equity": [1.0, 2.5, 0.5],
            "net_profit_margin": [15.0, 6.0, 12.0],
            "sector_name": ["Information Technology", "Automotive", "Consumer Goods"],
        })

        filtered = engine.apply_filters(df.copy(), "Quality_Compounder")
        assert len(filtered) >= 1

    def test_financial_sector_exclusion(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        engine = ScreenerEngine(config_path=config_path, db_path=":memory:")

        df = pd.DataFrame({
            "company_id": [1, 2],
            "roe": [18.0, 18.0],
            "revenue_cagr_3y": [12.0, 12.0],
            "cfo_quality": ["High Quality", "High Quality"],
            "debt_to_equity": [5.0, 5.0],
            "net_profit_margin": [12.0, 12.0],
            "sector_name": ["Information Technology", "Financial Services"],
        })

        filtered = engine.apply_filters(df.copy(), "Quality_Compounder")
        assert len(filtered) == 1

    def test_debt_free_icr(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        engine = ScreenerEngine(config_path=config_path, db_path=":memory:")

        df = pd.DataFrame({
            "company_id": [1, 2],
            "market_cap": [20000.0, 20000.0],
            "debt_to_equity": [0.05, 0.05],
            "roe": [15.0, 15.0],
            "net_profit_margin": [10.0, 10.0],
            "interest_coverage": [np.nan, 5.0],
            "sector_name": ["Consumer Goods", "Consumer Goods"],
        })

        filtered = engine.apply_filters(df.copy(), "Debt_Free_Blue_Chip")
        assert len(filtered) == 2

    def test_composite_score_range(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        engine = ScreenerEngine(config_path=config_path, db_path=":memory:")

        np.random.seed(42)
        n = 50
        df = pd.DataFrame({
            "company_id": range(1, n + 1),
            "roe": np.random.uniform(5, 30, n),
            "net_profit_margin": np.random.uniform(2, 25, n),
            "operating_profit_margin": np.random.uniform(5, 35, n),
            "cfo_quality": np.random.choice(
                ["High Quality", "Moderate", "Accrual Risk"], n
            ),
            "fcf_yield": np.random.uniform(-5, 15, n),
            "revenue_cagr_3y": np.random.uniform(-10, 30, n),
            "revenue_cagr_5y": np.random.uniform(-5, 25, n),
            "pat_cagr_3y": np.random.uniform(-15, 35, n),
            "pat_cagr_5y": np.random.uniform(-10, 30, n),
            "debt_to_equity": np.random.uniform(0, 3, n),
            "interest_coverage": np.random.uniform(0.5, 20, n),
        })

        engine.presets = engine.config["presets"]
        scored = engine.composite_score(df.copy())
        assert "composite_score" in scored.columns
        valid_scores = scored["composite_score"].dropna()
        assert valid_scores.min() >= 0.0
        assert valid_scores.max() <= 100.0

    def test_preset_has_required_keys(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "screener_config.yaml"
        )
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        required_keys = {"label", "filters", "sort_by", "composite_weights"}
        for preset_name, preset in config["presets"].items():
            missing = required_keys - set(preset.keys())
            assert not missing, f"Preset '{preset_name}' missing keys: {missing}"

            assert isinstance(preset["filters"], list)
            assert len(preset["filters"]) > 0
            assert isinstance(preset["sort_by"], str)
            weights = preset["composite_weights"]
            assert "profitability" in weights
            assert "cash_quality" in weights
            assert "growth" in weights
            assert "leverage" in weights
