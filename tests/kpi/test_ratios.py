import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analytics.cagr import compute_cagr
from src.analytics.cashflow_kpis import (
    capex_intensity_label,
    capex_intensity_pct,
    cfo_quality_label,
    classify_allocation,
    fcf_conversion_pct,
    free_cash_flow,
)
from src.analytics.ratios import (
    asset_turnover,
    book_value_per_share,
    debt_to_equity,
    interest_coverage_ratio,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    opm_cross_check,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)

# ══════════════════════════════════════════════════════════════════════════════
# Profitability ratios
# ══════════════════════════════════════════════════════════════════════════════


class TestNetProfitMargin:
    def test_normal(self):
        assert net_profit_margin(100, 1000) == pytest.approx(10.0)

    def test_zero_sales_returns_none(self):
        assert net_profit_margin(100, 0) is None

    def test_negative_profit(self):
        assert net_profit_margin(-100, 1000) == pytest.approx(-10.0)


class TestOperatingProfitMargin:
    def test_normal(self):
        assert operating_profit_margin(200, 1000) == pytest.approx(20.0)

    def test_zero_sales_returns_none(self):
        assert operating_profit_margin(200, 0) is None


class TestReturnOnEquity:
    def test_positive_equity(self):
        assert return_on_equity(100, 500, 500) == pytest.approx(10.0)

    def test_negative_equity_returns_none(self):
        assert return_on_equity(100, -500, -500) is None

    def test_zero_equity_returns_none(self):
        assert return_on_equity(100, 0, 0) is None


class TestReturnOnCapitalEmployed:
    def test_normal(self):
        assert return_on_capital_employed(300, 500, 500, 1000) == pytest.approx(15.0)

    def test_zero_capital_returns_none(self):
        assert return_on_capital_employed(300, 0, 0, 0) is None


class TestReturnOnAssets:
    def test_normal(self):
        assert return_on_assets(100, 2000) == pytest.approx(5.0)

    def test_zero_assets_returns_none(self):
        assert return_on_assets(100, 0) is None


# ══════════════════════════════════════════════════════════════════════════════
# Leverage & efficiency
# ══════════════════════════════════════════════════════════════════════════════


class TestDebtToEquity:
    def test_normal(self):
        assert debt_to_equity(1000, 500, 500) == pytest.approx(1.0)

    def test_debt_free_returns_zero(self):
        result = debt_to_equity(0, 500, 500)
        assert result == 0.0
        assert result is not None

    def test_negative_equity_returns_none(self):
        assert debt_to_equity(1000, -500, 0) is None


class TestInterestCoverage:
    def test_normal(self):
        assert interest_coverage_ratio(100, 20, 30) == pytest.approx(4.0)

    def test_zero_interest_returns_none(self):
        assert interest_coverage_ratio(100, 20, 0) is None

    def test_low_icr_detected(self):
        assert interest_coverage_ratio(100, 10, 80) == pytest.approx(1.375)


class TestNetDebt:
    def test_borrowings_minus_investments(self):
        assert net_debt(1000, 300) == pytest.approx(700.0)


class TestAssetTurnover:
    def test_normal(self):
        assert asset_turnover(5000, 10000) == pytest.approx(0.5)

    def test_zero_assets_returns_none(self):
        assert asset_turnover(5000, 0) is None


class TestBookValuePerShare:
    def test_normal(self):
        assert book_value_per_share(100, 900, 10) == pytest.approx(100.0)


class TestOpmCrossCheck:
    def test_divergence_detected(self):
        assert opm_cross_check(20.0, 13.53) is True

    def test_no_divergence(self):
        assert opm_cross_check(20.0, 20.0) is False


# ══════════════════════════════════════════════════════════════════════════════
# CAGR edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestCAGR:
    def test_normal_positive(self):
        value, flag = compute_cagr(100, 121, 2)
        assert value == pytest.approx(10.0)
        assert flag is None

    def test_decline_to_loss(self):
        value, flag = compute_cagr(100, -50, 2)
        assert value is None
        assert flag == "DECLINE_TO_LOSS"

    def test_turnaround(self):
        value, flag = compute_cagr(-50, 100, 2)
        assert value is None
        assert flag == "TURNAROUND"

    def test_both_negative(self):
        value, flag = compute_cagr(-100, -50, 3)
        assert value is None
        assert flag == "BOTH_NEGATIVE"

    def test_zero_base(self):
        value, flag = compute_cagr(0, 100, 2)
        assert value is None
        assert flag == "ZERO_BASE"

    def test_insufficient(self):
        value, flag = compute_cagr(100, 200, 0)
        assert value is None
        assert flag == "INSUFFICIENT"


# ══════════════════════════════════════════════════════════════════════════════
# Cash flow KPIs
# ══════════════════════════════════════════════════════════════════════════════


class TestFreeCashFlow:
    def test_fcf(self):
        assert free_cash_flow(1000, -500) == pytest.approx(500.0)

    def test_fcf_negative_allowed(self):
        assert free_cash_flow(200, -600) == pytest.approx(-400.0)


class TestCfoQuality:
    def test_high_quality(self):
        assert cfo_quality_label(1.5) == "High Quality"

    def test_moderate(self):
        assert cfo_quality_label(0.7) == "Moderate"

    def test_accrual_risk(self):
        assert cfo_quality_label(0.3) == "Accrual Risk"


class TestCapexIntensity:
    def test_asset_light(self):
        assert capex_intensity_label(capex_intensity_pct(-50, 5000)) == "Asset Light"

    def test_moderate(self):
        assert capex_intensity_label(capex_intensity_pct(-250, 5000)) == "Moderate"

    def test_capital_intensive(self):
        assert capex_intensity_label(capex_intensity_pct(-500, 5000)) == "Capital Intensive"


class TestFcfConversion:
    def test_normal(self):
        assert fcf_conversion_pct(500, 1000) == pytest.approx(50.0)

    def test_zero_operating_profit_returns_none(self):
        assert fcf_conversion_pct(500, 0) is None


class TestAllocationPatterns:
    def test_reinvestor(self):
        assert classify_allocation(100, -50, -30) == "Reinvestor"

    def test_shareholder_returns(self):
        assert classify_allocation(100, -50, -30, cfo_pat_ratio=1.5) == "Shareholder Returns"

    def test_distress_signal(self):
        assert classify_allocation(-100, 50, 30) == "Distress Signal"

    def test_cash_accumulator(self):
        assert classify_allocation(100, 50, 30) == "Cash Accumulator"
