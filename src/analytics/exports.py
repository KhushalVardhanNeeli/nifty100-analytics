"""Capital allocation CSV export and ratio edge-case cross-check — Sprint 2.

Generates:
  * output/capital_allocation.csv — 8-pattern label for every company-year
  * output/ratio_edge_cases.log — computed vs source ROE/ROCE anomalies
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

from src.analytics.cashflow_kpis import classify_allocation, _sign


def export_capital_allocation(db_path="db/nifty100.db", output_path=None):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "capital_allocation.csv")

    engine = create_engine(f"sqlite:///{db_path}")
    df = pd.read_sql_query(
        text("SELECT c.company_id, c.year, c.operating_activity, c.investing_activity, "
             "c.financing_activity, p.net_profit "
             "FROM cashflow c LEFT JOIN profitandloss p "
             "ON c.company_id = p.company_id AND c.year = p.year "
             "ORDER BY c.company_id, c.year"),
        engine)
    engine.dispose()

    if df.empty:
        print("[Allocation] No cashflow data found.")
        return pd.DataFrame()

    df["cfo_sign"] = df["operating_activity"].apply(_sign)
    df["cfi_sign"] = df["investing_activity"].apply(_sign)
    df["cff_sign"] = df["financing_activity"].apply(_sign)

    def _cfo_pat(r):
        if r["net_profit"] and pd.notna(r["net_profit"]) and r["net_profit"] != 0 \
                and pd.notna(r["operating_activity"]):
            return r["operating_activity"] / r["net_profit"]
        return None

    df["pattern_label"] = df.apply(
        lambda r: classify_allocation(r["operating_activity"], r["investing_activity"],
                                      r["financing_activity"], cfo_pat_ratio=_cfo_pat(r)),
        axis=1)

    out_df = df[["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"]]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, index=False)
    print(f"[Allocation] Exported {len(out_df)} rows to {output_path}")
    return out_df


def _categorise(source, calc):
    """Categorise a ROE/ROCE anomaly: data source issue, version difference, or formula discrepancy."""
    if source is None:
        return "missing source"
    if abs(source) < 1.0 or abs(source) > 200:
        return "data source issue"
    return "formula discrepancy"


def export_ratio_edge_cases(db_path="db/nifty100.db", output_path=None):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "ratio_edge_cases.log")

    engine = create_engine(f"sqlite:///{db_path}")

    latest = pd.read_sql_query(
        text("SELECT fr.company_id, fr.year, fr.return_on_equity_pct, "
             "fr.return_on_capital_employed_pct "
             "FROM financial_ratios fr "
             "JOIN (SELECT company_id, MAX(year) AS maxyr FROM financial_ratios GROUP BY company_id) t "
             "ON fr.company_id = t.company_id AND fr.year = t.maxyr"),
        engine)
    companies = pd.read_sql_query(
        text("SELECT company_id, ticker, roe_percentage, roce_percentage FROM companies"),
        engine)
    engine.dispose()

    anomalies = []
    for _, row in latest.iterrows():
        cid = row["company_id"]
        src = companies[companies["company_id"] == cid]
        if src.empty:
            continue
        src = src.iloc[0]
        ticker = src["ticker"]

        for metric, calc_col, src_col in [
            ("ROE", "return_on_equity_pct", "roe_percentage"),
            ("ROCE", "return_on_capital_employed_pct", "roce_percentage"),
        ]:
            calc = row[calc_col]
            sval = src[src_col]
            if calc is None or pd.isna(calc) or sval is None or pd.isna(sval) or sval == 0:
                continue
            rel_diff = abs(calc - sval) / abs(sval) * 100
            if rel_diff <= 5:
                continue
            anomalies.append({
                "ticker": ticker, "company_id": int(cid), "metric": metric,
                "computed": round(calc, 2), "source": round(sval, 2),
                "diff_pct": round(rel_diff, 2), "category": _categorise(sval, calc),
            })

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("Ratio Engine — Edge Case Cross-Check Log\n")
        f.write("=" * 72 + "\n")
        f.write("Computed latest-year ROE/ROCE vs companies.xlsx pre-computed values.\n")
        f.write("Anomalies flagged where relative difference > 5%.\n")
        f.write(f"Total anomalies: {len(anomalies)}\n\n")
        f.write(f"{'TICKER':<14}{'METRIC':<6}{'COMPUTED':>10}{'SOURCE':>10}{'DIFF%':>9}  CATEGORY\n")
        f.write("-" * 72 + "\n")
        for a in anomalies:
            f.write(f"{a['ticker']:<14}{a['metric']:<6}{a['computed']:>10}{a['source']:>10}"
                    f"{a['diff_pct']:>9}  {a['category']}\n")

    print(f"[EdgeCases] Logged {len(anomalies)} anomalies to {output_path}")
    return anomalies


def run_all_exports(db_path="db/nifty100.db"):
    print("[Exports] Running all exports...")
    export_capital_allocation(db_path)
    export_ratio_edge_cases(db_path)
    print("[Exports] Done.")


if __name__ == "__main__":
    run_all_exports()
