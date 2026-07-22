"""Capital allocation CSV export and ratio edge-case cross-check — Sprint 2."""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


def _classify_pattern(cfo, cfi, cff):
    if cfo is None or cfi is None or cff is None:
        return "Unknown"
    cfo_s = "+" if cfo > 0 else "-"
    cfi_s = "+" if cfi > 0 else "-"
    cff_s = "+" if cff > 0 else "-"
    mapping = {
        ("+", "-", "-"): "Healthy Growth",
        ("+", "-", "+"): "Growth + Fundraising",
        ("+", "+", "-"): "Asset Sale / Deleveraging",
        ("+", "+", "+"): "Cash Accumulation",
        ("-", "-", "-"): "Severe Stress",
        ("-", "-", "+"): "Funding Operations",
        ("-", "+", "-"): "Restructuring",
        ("-", "+", "+"): "Survival Mode",
    }
    return mapping.get((cfo_s, cfi_s, cff_s), f"({cfo_s},{cfi_s},{cff_s})")


def _sign(val):
    if val is None:
        return "0"
    return "+" if val > 0 else "-" if val < 0 else "0"


def export_capital_allocation(db_path="db/nifty100.db", output_path=None):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "capital_allocation.csv")

    engine = create_engine(f"sqlite:///{db_path}")

    df = pd.read_sql_query(
        text(
            "SELECT company_id, year, "
            "operating_activities, investing_activities, financing_activities "
            "FROM cashflow ORDER BY company_id, year"
        ),
        engine,
    )

    engine.dispose()

    if df.empty:
        print("[Allocation] No cashflow data found.")
        return

    df["cfo_sign"] = df["operating_activities"].apply(_sign)
    df["cfi_sign"] = df["investing_activities"].apply(_sign)
    df["cff_sign"] = df["financing_activities"].apply(_sign)
    df["pattern_label"] = df.apply(
        lambda r: _classify_pattern(
            r["operating_activities"],
            r["investing_activities"],
            r["financing_activities"],
        ),
        axis=1,
    )

    out_df = df[
        ["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"]
    ]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, index=False)
    print(f"[Allocation] Exported {len(out_df)} rows to {output_path}")


def export_ratio_edge_cases(db_path="db/nifty100.db", output_path=None):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "ratio_edge_cases.log")

    engine = create_engine(f"sqlite:///{db_path}")

    fr_df = pd.read_sql_query(
        text(
            "SELECT company_id, year, roe, roce "
            "FROM financial_ratios "
            "WHERE roe IS NOT NULL OR roce IS NOT NULL"
        ),
        engine,
    )

    pl_bs_df = pd.read_sql_query(
        text(
            "SELECT p.company_id, p.year, p.net_profit, p.operating_profit, p.sales, "
            "b.total_assets, b.current_liabilities, b.shareholders_equity "
            "FROM profitandloss p "
            "LEFT JOIN balancesheet b ON p.company_id = b.company_id AND p.year = b.year"
        ),
        engine,
    )

    companies_df = pd.read_sql_query(
        text("SELECT company_id, ticker FROM companies"),
        engine,
    )

    ticker_map = dict(zip(companies_df["company_id"], companies_df["ticker"]))

    engine.dispose()

    if fr_df.empty:
        print("[EdgeCases] No ratio data found.")
        return

    anomalies = []

    for _, row in fr_df.iterrows():
        cid = row["company_id"]
        yr = row["year"]
        stored_roe = row["roe"]
        stored_roce = row["roce"]

        src = pl_bs_df[
            (pl_bs_df["company_id"] == cid) & (pl_bs_df["year"] == yr)
        ]
        if src.empty:
            continue

        src = src.iloc[0]
        net_profit = src.get("net_profit")
        op_profit = src.get("operating_profit")
        total_assets = src.get("total_assets")
        cur_liab = src.get("current_liabilities")
        equity = src.get("shareholders_equity")

        tag = f"{cid}:{yr}"

        # Cross-check ROE
        if stored_roe is not None and not pd.isna(stored_roe):
            if equity and equity > 0 and net_profit is not None:
                calc_roe = net_profit / equity * 100
            else:
                calc_roe = None

            if calc_roe is not None:
                diff = abs(stored_roe - calc_roe)
                pct_diff = (diff / abs(calc_roe) * 100) if calc_roe != 0 else None

                category = "OK"
                if pct_diff is not None and pct_diff > 1:
                    category = (
                        "Significant Discrepancy"
                        if pct_diff > 5
                        else "Minor Discrepancy"
                    )

                anomalies.append({
                    "tag": tag,
                    "metric": "ROE",
                    "stored": round(stored_roe, 2),
                    "calculated": round(calc_roe, 2),
                    "diff_pct": round(pct_diff, 2) if pct_diff is not None else None,
                    "category": category,
                })

        # Cross-check ROCE
        if stored_roce is not None and not pd.isna(stored_roce):
            denom = total_assets - (cur_liab or 0)
            if denom and denom > 0 and op_profit is not None:
                calc_roce = op_profit / denom * 100
            else:
                calc_roce = None

            if calc_roce is not None:
                diff = abs(stored_roce - calc_roce)
                pct_diff = (diff / abs(calc_roce) * 100) if calc_roce != 0 else None

                category = "OK"
                if pct_diff is not None and pct_diff > 1:
                    category = (
                        "Significant Discrepancy"
                        if pct_diff > 5
                        else "Minor Discrepancy"
                    )

                anomalies.append({
                    "tag": tag,
                    "metric": "ROCE",
                    "stored": round(stored_roce, 2),
                    "calculated": round(calc_roce, 2),
                    "diff_pct": round(pct_diff, 2) if pct_diff is not None else None,
                    "category": category,
                })

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("Ratio Engine — Edge Case Cross-Check Log\n")
        f.write("=" * 70 + "\n")
        f.write(f"Total anomalies checked: {len(anomalies)}\n\n")
        for a in anomalies:
            f.write(
                f"{a['tag']} | {a['metric']} | "
                f"STORED={a['stored']} | CALCULATED={a['calculated']} | "
                f"DIFF={a['diff_pct']}% | {a['category']}\n"
            )

    print(f"[EdgeCases] Logged {len(anomalies)} cross-checks to {output_path}")


def run_all_exports(db_path="db/nifty100.db"):
    print("[Exports] Running all exports...")
    export_capital_allocation(db_path)
    export_ratio_edge_cases(db_path)
    print("[Exports] Done.")


if __name__ == "__main__":
    run_all_exports()
