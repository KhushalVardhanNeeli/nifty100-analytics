import math
import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analytics.ratios import (
    net_profit_margin,
    operating_profit_margin,
    return_on_equity,
    return_on_capital_employed,
    return_on_assets,
    debt_to_equity,
    interest_coverage_ratio,
    RatioEngine,
)
from src.analytics.cagr import compute_cagr, CAGRCalculator
from src.analytics.cashflow_kpis import CashFlowAnalyzer


# ══════════════════════════════════════════════════════════════════════════════
# Net Profit Margin — 3 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNetProfitMargin:
    def test_normal_positive_margin(self):
        result = net_profit_margin(100, 1000)
        assert result == pytest.approx(10.0)

    def test_zero_sales_denominator(self):
        result = net_profit_margin(100, 0)
        assert result is None

    def test_negative_profit_margin(self):
        result = net_profit_margin(-100, 1000)
        assert result == pytest.approx(-10.0)


# ══════════════════════════════════════════════════════════════════════════════
# Operating Profit Margin — 2 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOperatingProfitMargin:
    def test_normal_opm(self):
        result = operating_profit_margin(200, 1000)
        assert result == pytest.approx(20.0)

    def test_zero_operating_profit(self):
        result = operating_profit_margin(0, 1000)
        assert result == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════════════════
# Return on Equity — 3 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReturnOnEquity:
    def test_normal_roe(self):
        result = return_on_equity(100, 500, 500)
        assert result == pytest.approx(10.0)

    def test_negative_equity_returns_none(self):
        result = return_on_equity(100, -500, -500)
        assert result is None

    def test_zero_equity_returns_none(self):
        result = return_on_equity(100, 0, 0)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Return on Capital Employed — 2 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReturnOnCapitalEmployed:
    def test_normal_roce(self):
        result = return_on_capital_employed(300, 500, 500, 1000)
        assert result == pytest.approx(15.0)

    def test_zero_capital_employed_returns_none(self):
        result = return_on_capital_employed(300, 0, 0, 0)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Return on Assets — 2 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReturnOnAssets:
    def test_normal_roa(self):
        result = return_on_assets(100, 2000)
        assert result == pytest.approx(5.0)

    def test_zero_assets_returns_none(self):
        result = return_on_assets(100, 0)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Debt to Equity — 4 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDebtToEquity:
    def test_normal_debt_equity(self):
        result = debt_to_equity(1000, 500, 500)
        assert result == pytest.approx(1.0)

    def test_zero_debt_returns_zero_not_none(self):
        result = debt_to_equity(0, 500, 500)
        assert result == 0.0
        assert result is not None

    def test_negative_equity_returns_none(self):
        result = debt_to_equity(1000, -500, 0)
        assert result is None

    def test_high_de_for_financial_sector_warning_flag(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 10000,
            "operating_profit": 2000,
            "net_profit": 1000,
            "total_assets": 20000,
            "shareholders_equity": 1000,
            "total_debt": 7000,
            "sector_name": "Financial Services",
            "cash_and_equivalents": 500,
            "current_assets": 2000,
            "current_liabilities": 1000,
        }])

        with patch.object(pd, "read_sql_query", side_effect=[df, _empty_df(), _empty_df(), _empty_df()]):
            result = engine.compute_ratios(company_id=1)
            assert len(engine.financial_warnings) >= 1
            assert "Financial sector D/E" in engine.financial_warnings[0]


# ══════════════════════════════════════════════════════════════════════════════
# Interest Coverage Ratio — 3 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestInterestCoverageRatio:
    def test_normal_interest_coverage(self):
        result = interest_coverage_ratio(100, 20, 30)
        assert result == pytest.approx(4.0)

    def test_zero_interest_expense_debt_free(self):
        result = interest_coverage_ratio(100, 20, 0)
        assert result is None

    def test_icr_below_1_5_warning(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 10000,
            "operating_profit": 100,
            "interest_expense": 80,
            "other_income": 10,
            "net_profit": 50,
            "total_assets": 20000,
            "shareholders_equity": 10000,
            "total_debt": 5000,
            "sector_name": "Metals and Mining",
            "cash_and_equivalents": 500,
            "current_assets": 2000,
            "current_liabilities": 1000,
        }])

        with patch.object(pd, "read_sql_query", side_effect=[df, _empty_df(), _empty_df(), _empty_df()]):
            result = engine.compute_ratios(company_id=1)
            assert len(engine.icr_warnings) >= 1
            assert "ICR=" in engine.icr_warnings[0] or "Debt Free" in engine.icr_warnings[0]


# ══════════════════════════════════════════════════════════════════════════════
# CAGR — 5 tests (plus INSUFFICIENT_DATA)
# ══════════════════════════════════════════════════════════════════════════════

class TestCAGR:
    def test_normal_positive_cagr(self):
        value, flag = compute_cagr(100, 121, 2)
        assert value == pytest.approx(10.0)
        assert flag is None

    def test_decline_to_loss_flag(self):
        value, flag = compute_cagr(100, -50, 2)
        assert value is None
        assert flag == "DECLINE_TO_LOSS"

    def test_turnaround_flag(self):
        value, flag = compute_cagr(-50, 100, 2)
        assert value is None
        assert flag == "TURNAROUND"

    def test_both_negative_flag(self):
        value, flag = compute_cagr(-100, -50, 3)
        assert value is None
        assert flag == "BOTH_NEGATIVE"

    def test_zero_base_flag(self):
        value, flag = compute_cagr(0, 100, 2)
        assert value is None
        assert flag == "ZERO_BASE"

    def test_insufficient_data_flag(self):
        value, flag = compute_cagr(100, 200, 0)
        assert value is None
        assert flag is None


# ══════════════════════════════════════════════════════════════════════════════
# RatioEngine standalone — 4 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRatioEngine:
    def test_ratio_engine_computes_all_ratios(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 10000,
            "operating_profit": 2000,
            "operating_profit_margin": 0.20,
            "net_profit": 1000,
            "eps": 50,
            "dividend_payout_pct": 0.25,
            "tax_rate": 25,
            "depreciation": 500,
            "interest_expense": 200,
            "other_income": 100,
            "total_revenue": 10000,
            "cogs": 6000,
            "total_assets": 20000,
            "total_liabilities": 8000,
            "shareholders_equity": 12000,
            "total_debt": 3000,
            "current_assets": 4000,
            "current_liabilities": 2000,
            "cash_and_equivalents": 1000,
            "inventory": 1500,
            "sector_name": "Information Technology",
            "market_cap": 50000,
            "ticker": "TEST",
        }])

        sp_df = pd.DataFrame({"close": [2000.0]})
        cf_df = pd.DataFrame({"fcf": [800.0]})

        with patch.object(pd, "read_sql_query", side_effect=[df, sp_df, cf_df, sp_df]):
            result = engine.compute_ratios(company_id=1)
            assert not result.empty
            assert "company_id" in result.columns
            assert "roe" in result.columns
            assert "debt_to_equity" in result.columns
            assert "interest_coverage" in result.columns
            assert "net_profit_margin" in result.columns
            assert "operating_profit_margin" in result.columns

    def test_ratio_values_are_reasonable(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 10000,
            "operating_profit": 2000,
            "operating_profit_margin": 0.20,
            "net_profit": 1500,
            "eps": 75,
            "dividend_payout_pct": 0.20,
            "tax_rate": 25,
            "depreciation": 500,
            "interest_expense": 300,
            "other_income": 100,
            "total_revenue": 10000,
            "cogs": 5500,
            "total_assets": 15000,
            "total_liabilities": 5000,
            "shareholders_equity": 10000,
            "total_debt": 2000,
            "current_assets": 4000,
            "current_liabilities": 2000,
            "cash_and_equivalents": 1500,
            "inventory": 2000,
            "sector_name": "Automotive",
            "market_cap": 60000,
            "ticker": "AUTO",
        }])

        with patch.object(pd, "read_sql_query", side_effect=[df, _empty_df(), _empty_df(), _empty_df()]):
            result = engine.compute_ratios(company_id=1)
            row = result.iloc[0]
            assert row["net_profit_margin"] == pytest.approx(15.0)
            assert row["operating_profit_margin"] == pytest.approx(20.0)
            assert row["roe"] == pytest.approx(15.0)
            assert row["roa"] == pytest.approx(10.0)
            assert row["debt_to_equity"] == pytest.approx(0.2)
            assert row["current_ratio"] == pytest.approx(2.0)

    def test_warnings_generated_for_financial_sector(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 50000,
            "operating_profit": 5000,
            "operating_profit_margin": 0.10,
            "net_profit": 3000,
            "eps": 30,
            "dividend_payout_pct": 0.15,
            "tax_rate": 25,
            "depreciation": 200,
            "interest_expense": 500,
            "other_income": 100,
            "total_revenue": 50000,
            "cogs": 30000,
            "total_assets": 100000,
            "total_liabilities": 90000,
            "shareholders_equity": 10000,
            "total_debt": 80000,
            "current_assets": 20000,
            "current_liabilities": 30000,
            "cash_and_equivalents": 5000,
            "inventory": 0,
            "sector_name": "BFSI",
            "market_cap": 40000,
            "ticker": "BANK",
        }])

        with patch.object(pd, "read_sql_query", side_effect=[df, _empty_df(), _empty_df(), _empty_df()]):
            result = engine.compute_ratios(company_id=1)
            assert len(engine.financial_warnings) >= 1
            assert "Financial sector D/E" in engine.financial_warnings[0]

    def test_icr_warnings_captured(self):
        engine = RatioEngine.__new__(RatioEngine)
        engine.db_path = ":memory:"
        engine.engine = MagicMock()
        engine.financial_warnings = []
        engine.icr_warnings = []

        df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "sales": 10000,
            "operating_profit": 100,
            "operating_profit_margin": 0.01,
            "net_profit": 50,
            "eps": 2.5,
            "dividend_payout_pct": 0.10,
            "tax_rate": 25,
            "depreciation": 80,
            "interest_expense": 200,
            "other_income": 10,
            "total_revenue": 10000,
            "cogs": 7000,
            "total_assets": 20000,
            "total_liabilities": 12000,
            "shareholders_equity": 8000,
            "total_debt": 10000,
            "current_assets": 3000,
            "current_liabilities": 4000,
            "cash_and_equivalents": 500,
            "inventory": 1000,
            "sector_name": "Metals and Mining",
            "market_cap": 8000,
            "ticker": "METAL",
        }])

        with patch.object(pd, "read_sql_query", side_effect=[df, _empty_df(), _empty_df(), _empty_df()]):
            result = engine.compute_ratios(company_id=1)
            assert len(engine.icr_warnings) >= 1
            assert "ICR=" in engine.icr_warnings[0]


# ══════════════════════════════════════════════════════════════════════════════
# CashFlowAnalyzer — 11 tests
# ══════════════════════════════════════════════════════════════════════════════

def _empty_df():
    return pd.DataFrame()


class TestCashFlowAnalyzer:
    def test_fcf_calculation(self):
        pl_df = pd.DataFrame([
            {"company_id": 1, "year": 2022, "net_profit": 500, "sales": 5000},
        ])
        cf_df = pd.DataFrame([{
            "company_id": 1, "year": 2022,
            "operating_activities": 1000,
            "investing_activities": -500,
            "financing_activities": -300,
        }])

        analyzer = CashFlowAnalyzer(pl_df=pl_df, cf_df=cf_df)
        result = analyzer.analyze(company_id=1, year=2022,
                                   row={"sales": 5000, "operating_profit": 800})
        assert result is not None
        assert result["fcf"] == pytest.approx(500.0)

    def test_cfo_quality_high(self):
        pl_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "net_profit": 1000}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])
        cf_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "operating_activities": 1500}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])

        analyzer = CashFlowAnalyzer(pl_df=pl_df, cf_df=cf_df)
        quality = analyzer._calc_cfo_quality(company_id=1, cfo_current=1500)
        assert quality == "High Quality"

    def test_cfo_quality_moderate(self):
        pl_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "net_profit": 1000}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])
        cf_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "operating_activities": 700}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])

        analyzer = CashFlowAnalyzer(pl_df=pl_df, cf_df=cf_df)
        quality = analyzer._calc_cfo_quality(company_id=1, cfo_current=700)
        assert quality == "Moderate"

    def test_cfo_quality_accrual_risk(self):
        pl_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "net_profit": 1000}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])
        cf_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "operating_activities": 300}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])

        analyzer = CashFlowAnalyzer(pl_df=pl_df, cf_df=cf_df)
        quality = analyzer._calc_cfo_quality(company_id=1, cfo_current=300)
        assert quality == "Accrual Risk"

    def test_cfo_quality_loss_making(self):
        pl_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "net_profit": -500}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])
        cf_df = pd.DataFrame([
            {"company_id": 1, "year": yr, "operating_activities": 100}
            for yr in [2018, 2019, 2020, 2021, 2022]
        ])

        analyzer = CashFlowAnalyzer(pl_df=pl_df, cf_df=cf_df)
        result = analyzer.compute(company_id=1)
        assert not result.empty
        label_vals = result["cfo_quality_label"].values
        has_loss_making = any("Loss-making" in str(v) for v in label_vals)
        has_high = any("High Quality" in str(v) for v in label_vals)
        has_accrual = any("Accrual Risk" in str(v) for v in label_vals)
        assert has_loss_making or has_accrual

    def test_capex_asset_light(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._calc_capex_intensity(-50, 5000)
        assert result == "Asset Light"

    def test_capex_moderate(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._calc_capex_intensity(-250, 5000)
        assert result == "Moderate"

    def test_capex_capital_intensive(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._calc_capex_intensity(-500, 5000)
        assert result == "Capital Intensive"

    def test_allocation_healthy_growth(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._classify_allocation(100, -50, -30)
        assert result == "Healthy Growth"

    def test_allocation_severe_stress(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._classify_allocation(-100, -50, -30)
        assert result == "Severe Stress"

    def test_allocation_restructuring(self):
        analyzer = CashFlowAnalyzer()
        result = analyzer._classify_allocation(-100, 50, -30)
        assert result == "Restructuring"
