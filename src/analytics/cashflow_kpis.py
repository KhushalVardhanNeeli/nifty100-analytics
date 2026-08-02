"""Cash Flow KPIs — FCF, CFO quality, CapEx intensity, FCF conversion,
and the 8-pattern capital allocation classifier (Sprint 2).

Uses the spec-aligned cashflow table columns: operating_activity,
investing_activity, financing_activity, net_cash_flow.
"""

import os
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")


# ── Standalone functions (unit-testable) ──────────────────────────────

def free_cash_flow(operating_activity: float, investing_activity: float) -> Optional[float]:
    """FCF = operating_activity + investing_activity. Negative is allowed."""
    if operating_activity is None or investing_activity is None:
        return None
    return operating_activity + investing_activity


def cfo_quality_label(avg_cfo_pat: Optional[float]) -> Optional[str]:
    """Map the 5-year average CFO/PAT ratio to a quality label."""
    if avg_cfo_pat is None:
        return None
    if avg_cfo_pat > 1.0:
        return "High Quality"
    if avg_cfo_pat >= 0.5:
        return "Moderate"
    return "Accrual Risk"


def capex_intensity_pct(investing_activity: float, sales: float) -> Optional[float]:
    """CapEx intensity = abs(investing_activity) / sales * 100."""
    if not sales or sales == 0 or investing_activity is None:
        return None
    return abs(investing_activity) / sales * 100


def capex_intensity_label(intensity_pct: Optional[float]) -> Optional[str]:
    if intensity_pct is None:
        return None
    if intensity_pct < 3:
        return "Asset Light"
    if intensity_pct <= 8:
        return "Moderate"
    return "Capital Intensive"


def fcf_conversion_pct(fcf: float, operating_profit: float) -> Optional[float]:
    """FCF conversion = FCF / operating_profit * 100."""
    if not operating_profit or operating_profit == 0 or fcf is None:
        return None
    return fcf / operating_profit * 100


def _sign(v) -> str:
    if v is None:
        return "-"
    return "+" if v > 0 else "-"


def classify_allocation(cfo, cfi, cff, cfo_pat_ratio: Optional[float] = None) -> str:
    """8-pattern capital allocation classifier based on (CFO, CFI, CFF) signs."""
    s = (_sign(cfo), _sign(cfi), _sign(cff))
    if s == ("+", "-", "-"):
        if cfo_pat_ratio is not None and cfo_pat_ratio > 1.0:
            return "Shareholder Returns"
        return "Reinvestor"
    if s == ("+", "+", "-"):
        return "Liquidating Assets"
    if s == ("-", "+", "+"):
        return "Distress Signal"
    if s == ("-", "-", "+"):
        return "Growth Funded by Debt"
    if s == ("+", "+", "+"):
        return "Cash Accumulator"
    if s == ("-", "-", "-"):
        return "Pre-Revenue"
    if s == ("+", "-", "+"):
        return "Mixed"
    if s == ("-", "+", "-"):
        return "Restructuring"
    return "Unknown"


# ── Analyzer ─────────────────────────────────────────────────────────

class CashFlowAnalyzer:
    """Computes cash-flow KPIs per company-year from P&L + cashflow tables."""

    def __init__(self, db_path: str = "db/nifty100.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")

    def compute(self, company_id=None) -> pd.DataFrame:
        cf = pd.read_sql_query(
            text("SELECT company_id, year, operating_activity, investing_activity, "
                 "financing_activity, net_cash_flow FROM cashflow"), self.engine)
        pl = pd.read_sql_query(
            text("SELECT company_id, year, sales, operating_profit, net_profit FROM profitandloss"),
            self.engine)
        if cf.empty or pl.empty:
            return pd.DataFrame()

        if company_id is not None:
            cf = cf[cf["company_id"] == company_id]
            pl = pl[pl["company_id"] == company_id]

        # Per-year CFO/PAT ratio, then a trailing 5-year average per company.
        merged = pl.merge(cf, on=["company_id", "year"], how="inner", suffixes=("", "_cf"))
        merged["cfo_pat"] = merged.apply(
            lambda r: (r["operating_activity"] / r["net_profit"])
            if r["net_profit"] and r["net_profit"] != 0 and pd.notna(r["operating_activity"])
            else None, axis=1)

        rows = []
        for cid, grp in merged.groupby("company_id"):
            grp = grp.sort_values("year")
            cfo_pat_series = grp["cfo_pat"].tolist()
            for i, (_, r) in enumerate(grp.iterrows()):
                window = [x for x in cfo_pat_series[max(0, i - 4): i + 1] if x is not None]
                avg = sum(window) / len(window) if window else None

                fcf = free_cash_flow(r["operating_activity"], r["investing_activity"])
                intensity = capex_intensity_pct(r["investing_activity"], r["sales"])
                pattern = classify_allocation(
                    r["operating_activity"], r["investing_activity"],
                    r["financing_activity"], cfo_pat_ratio=(r["cfo_pat"] if pd.notna(r["cfo_pat"]) else None))

                rows.append({
                    "company_id": int(cid),
                    "year": int(r["year"]),
                    "free_cash_flow_cr": fcf,
                    "cfo_quality_score": round(avg, 4) if avg is not None else None,
                    "cfo_quality_label": cfo_quality_label(avg),
                    "capex_intensity_pct": round(intensity, 4) if intensity is not None else None,
                    "capex_intensity_label": capex_intensity_label(intensity),
                    "fcf_conversion_pct": round(fcf_conversion_pct(fcf, r["operating_profit"]), 4)
                    if fcf_conversion_pct(fcf, r["operating_profit"]) is not None else None,
                    "capital_allocation_pattern": pattern,
                })
        return pd.DataFrame(rows)

    def run(self):
        return self.compute()


if __name__ == "__main__":
    analyzer = CashFlowAnalyzer()
    df = analyzer.run()
    print(f"[CashFlowAnalyzer] Processed {len(df)} rows")
