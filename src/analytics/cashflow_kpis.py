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
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


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


# ── Sprint 5: Cash Flow Intelligence ─────────────────────────────────

def build_cashflow_intelligence(db_path: str = DB_PATH) -> pd.DataFrame:
    """Build per-company cash-flow intelligence and export Excel + alerts.

    Columns: company_id, sector, cfo_quality_score, cfo_quality_label,
    capex_intensity_pct, capex_label, fcf_cagr_5yr, fcf_conversion_pct,
    distress_flag, deleveraging_flag, capital_allocation_label.
    """
    from src.analytics.cagr import compute_cagr

    engine = create_engine(f"sqlite:///{db_path}")
    companies = pd.read_sql(text("SELECT company_id, ticker, broad_sector FROM companies"), engine)
    cf = pd.read_sql(text("SELECT * FROM cashflow ORDER BY company_id, year"), engine)
    pl = pd.read_sql(text("SELECT company_id, year, sales, operating_profit, net_profit "
                          "FROM profitandloss ORDER BY company_id, year"), engine)
    bs = pd.read_sql(text("SELECT company_id, year, borrowings FROM balancesheet "
                          "ORDER BY company_id, year"), engine)
    engine.dispose()

    kpis = CashFlowAnalyzer(db_path).compute()
    latest_year = cf["year"].max()

    rows = []
    for cid, grp in cf.groupby("company_id"):
        grp = grp.sort_values("year")
        latest = grp[grp["year"] == latest_year]

        # FCF 5-year CAGR
        fcf_series = (grp["operating_activity"].fillna(0) + grp["investing_activity"].fillna(0)).tolist()
        fcf_cagr = None
        if len(fcf_series) >= 6:
            val, _ = compute_cagr(fcf_series[-6], fcf_series[-1], 5)
            fcf_cagr = val

        # Distress: CFO < 0 AND CFF > 0 in latest year
        distress = False
        cfo_val = cff_val = None
        if not latest.empty:
            r = latest.iloc[0]
            cfo_val = r["operating_activity"]
            cff_val = r["financing_activity"]
            distress = bool(cfo_val < 0 and cff_val > 0)

        # Deleveraging: CFF < 0 AND borrowings declining YoY
        deleveraging = False
        bs_c = bs[bs["company_id"] == cid].sort_values("year")
        if not latest.empty and len(bs_c) >= 2:
            cff_now = latest.iloc[0]["financing_activity"]
            b_now = bs_c.iloc[-1]["borrowings"]
            b_prev = bs_c.iloc[-2]["borrowings"]
            if cff_now is not None and cff_now < 0 and b_now is not None and b_prev is not None \
                    and b_now < b_prev:
                deleveraging = True

        kpi_row = kpis[kpis["company_id"] == cid]
        sector_row = companies[companies["company_id"] == cid]
        rows.append({
            "company_id": int(cid),
            "ticker": sector_row.iloc[0]["ticker"] if not sector_row.empty else None,
            "sector": sector_row.iloc[0]["broad_sector"] if not sector_row.empty else None,
            "cfo_quality_score": kpi_row.iloc[0]["cfo_quality_score"] if not kpi_row.empty else None,
            "cfo_quality_label": kpi_row.iloc[0]["cfo_quality_label"] if not kpi_row.empty else None,
            "capex_intensity_pct": kpi_row.iloc[0]["capex_intensity_pct"] if not kpi_row.empty else None,
            "capex_label": kpi_row.iloc[0]["capex_intensity_label"] if not kpi_row.empty else None,
            "fcf_cagr_5yr": round(fcf_cagr, 2) if fcf_cagr is not None else None,
            "fcf_conversion_pct": kpi_row.iloc[0]["fcf_conversion_pct"] if not kpi_row.empty else None,
            "distress_flag": distress,
            "deleveraging_flag": bool(deleveraging),
            "capital_allocation_label": kpi_row.iloc[0]["capital_allocation_pattern"]
            if not kpi_row.empty else None,
            "cfo_latest": cfo_val,
            "cff_latest": cff_val,
        })

    out = pd.DataFrame(rows)
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out.to_excel(os.path.join(OUTPUT_DIR, "cashflow_intelligence.xlsx"), index=False)

    alerts = out[out["distress_flag"]]
    if not alerts.empty:
        net_profit_map = pl[pl["year"] == latest_year].set_index("company_id")["net_profit"].to_dict()
        alerts["latest_net_profit"] = alerts["company_id"].map(net_profit_map)
        alerts[["company_id", "ticker", "sector", "cfo_latest", "cff_latest", "latest_net_profit"]] \
            .to_csv(os.path.join(OUTPUT_DIR, "distress_alerts.csv"), index=False)

    print(f"[CashFlowIntel] Exported {len(out)} rows; {len(alerts)} distress alerts")
    return out


def capital_allocation_report(db_path: str = DB_PATH):
    """Distribution summary + year-over-year pattern changes (Day 32)."""
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    ca = pd.read_sql(text("SELECT company_id, year, operating_activity, investing_activity, "
                          "financing_activity FROM cashflow ORDER BY company_id, year"), engine)
    engine.dispose()

    ca["pattern"] = ca.apply(
        lambda r: classify_allocation(r["operating_activity"], r["investing_activity"],
                                      r["financing_activity"]), axis=1)

    latest_year = ca["year"].max()
    latest = ca[ca["year"] == latest_year]
    dist = latest["pattern"].value_counts().rename("count").reset_index()
    dist.columns = ["pattern", "count"]
    dist.to_csv(os.path.join(OUTPUT_DIR, "capital_allocation_distribution.csv"), index=False)

    changes = []
    for cid, grp in ca.groupby("company_id"):
        grp = grp.sort_values("year")
        for i in range(1, len(grp)):
            if grp.iloc[i]["pattern"] != grp.iloc[i - 1]["pattern"]:
                changes.append({
                    "company_id": int(cid),
                    "year": int(grp.iloc[i]["year"]),
                    "prev_pattern": grp.iloc[i - 1]["pattern"],
                    "new_pattern": grp.iloc[i]["pattern"],
                })
    changes_df = pd.DataFrame(changes)
    changes_df.to_csv(os.path.join(OUTPUT_DIR, "pattern_changes.csv"), index=False)
    print(f"[CashFlowIntel] Pattern distribution: {len(dist)} patterns; "
          f"{len(changes_df)} year-over-year changes")
    return dist, changes_df


if __name__ == "__main__":
    build_cashflow_intelligence()
    capital_allocation_report()
