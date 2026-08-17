"""Valuation Module — Sprint 4.

Uses market_cap data to compute FCF yield, sector-relative P/E flags
(Caution / Discount / Fair) and exports:
  * output/valuation_summary.xlsx
  * output/valuation_flags.csv (Caution / Discount only)
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


def compute_valuation(db_path: str = DB_PATH) -> pd.DataFrame:
    engine = create_engine(f"sqlite:///{db_path}")

    latest = int(pd.read_sql(text("SELECT MAX(year) AS y FROM market_cap"), engine).iloc[0]["y"])

    mc_latest = pd.read_sql(
        text("SELECT * FROM market_cap WHERE year = :y"), engine, params={"y": latest})
    mc_all = pd.read_sql(text("SELECT company_id, year, pe_ratio FROM market_cap"), engine)
    companies = pd.read_sql(
        text("SELECT company_id, ticker, company_name, broad_sector FROM companies"), engine)
    fr = pd.read_sql(
        text("SELECT company_id, year, free_cash_flow_cr FROM financial_ratios WHERE year = :y"),
        engine, params={"y": latest})

    df = (mc_latest.merge(companies, on="company_id", how="left")
                    .merge(fr, on=["company_id", "year"], how="left"))

    df["sector"] = df["broad_sector"]
    sector_medians = df.groupby("sector")["pe_ratio"].median().to_dict()
    df["sector_median_PE"] = df["sector"].map(sector_medians)

    five_yr = (mc_all.groupby("company_id")["pe_ratio"]
                     .median().rename("five_yr_median_PE"))
    df = df.merge(five_yr, on="company_id", how="left")

    df["FCF_yield_pct"] = df.apply(
        lambda r: (r["free_cash_flow_cr"] / r["market_cap_crore"] * 100)
        if pd.notna(r["free_cash_flow_cr"]) and r["market_cap_crore"]
        else None, axis=1)
    df["PE_vs_sector_median_pct"] = df.apply(
        lambda r: (r["pe_ratio"] / r["sector_median_PE"] * 100)
        if pd.notna(r["pe_ratio"]) and pd.notna(r["sector_median_PE"]) and r["sector_median_PE"]
        else None, axis=1)

    def _flag(r):
        pe, sm = r["pe_ratio"], r["sector_median_PE"]
        if pd.isna(pe) or pd.isna(sm) or sm == 0:
            return None
        if pe > sm * 1.5:
            return "Caution"
        if pe < sm * 0.7:
            return "Discount"
        return "Fair"

    df["flag"] = df.apply(_flag, axis=1)

    out = df[["company_id", "company_name", "sector", "pe_ratio", "pb_ratio",
              "ev_ebitda", "FCF_yield_pct", "five_yr_median_PE",
              "PE_vs_sector_median_pct", "flag"]].copy()
    out = out.rename(columns={"pe_ratio": "P/E", "pb_ratio": "P/B", "ev_ebitda": "EV/EBITDA"})
    engine.dispose()
    return out


def export_valuation(db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> tuple:
    df = compute_valuation(db_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    summary_path = os.path.join(output_dir, "valuation_summary.xlsx")
    flags_path = os.path.join(output_dir, "valuation_flags.csv")

    df.to_excel(summary_path, index=False)
    flags = df[df["flag"].isin(["Caution", "Discount"])]
    flags.to_csv(flags_path, index=False)

    print(f"[Valuation] Exported {len(df)} rows to {summary_path}")
    print(f"[Valuation] Exported {len(flags)} flagged rows to {flags_path}")
    return summary_path, flags_path


if __name__ == "__main__":
    export_valuation()
