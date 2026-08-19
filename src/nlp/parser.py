"""Analysis text parser — Sprint 5 (Day 29).

Parses the text fields in analysis.xlsx (loaded into the `analysis` table)
into structured (period, value) rows using the spec regex:
    (\\d+)\\s*Years?:?\\s*([\\d.]+)%

Exports:
  * output/analysis_parsed.csv   — company_id, metric_type, period_years, value_pct
  * output/parse_failures.csv    — text entries that did not match
  * output/cagr_crosscheck.csv   — parsed vs ratio-engine CAGR divergences > 5%
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

PATTERN = r"(\d+)\s*Years?:?\s*([\d.]+)%"
METRIC_FIELDS = [
    "compounded_sales_growth",
    "compounded_profit_growth",
    "stock_price_cagr",
    "roe",
]

# metric_type -> computed CAGR column in financial_ratios
CAGR_MAP = {
    "compounded_sales_growth": {
        3: "revenue_cagr_3yr",
        5: "revenue_cagr_5yr",
        10: "revenue_cagr_10yr",
    },
    "compounded_profit_growth": {
        3: "pat_cagr_3yr",
        5: "pat_cagr_5yr",
        10: "pat_cagr_10yr",
    },
}


def parse_text(value: str):
    """Return (period_years, value_pct) or None if no match."""
    if value is None or not str(value).strip():
        return None
    import re

    m = re.search(PATTERN, str(value))
    if not m:
        return None
    return int(m.group(1)), float(m.group(2))


def parse_analysis(db_path: str = DB_PATH) -> tuple:
    engine = create_engine(f"sqlite:///{db_path}")
    df = pd.read_sql(text("SELECT * FROM analysis"), engine)
    engine.dispose()

    parsed_rows, failures = [], []
    for _, row in df.iterrows():
        cid = row["company_id"]
        for field in METRIC_FIELDS:
            val = row.get(field)
            if val is None or not str(val).strip():
                continue
            parsed = parse_text(val)
            if parsed is None:
                failures.append(
                    {
                        "company_id": int(cid),
                        "metric_type": field,
                        "text": str(val),
                    }
                )
            else:
                period, value = parsed
                parsed_rows.append(
                    {
                        "company_id": int(cid),
                        "metric_type": field,
                        "period_years": period,
                        "value_pct": value,
                    }
                )

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    parsed_df = pd.DataFrame(parsed_rows)
    fail_df = pd.DataFrame(failures)
    parsed_df.to_csv(os.path.join(OUTPUT_DIR, "analysis_parsed.csv"), index=False)
    fail_df.to_csv(os.path.join(OUTPUT_DIR, "parse_failures.csv"), index=False)
    print(f"[NLP] Parsed {len(parsed_df)} values, {len(fail_df)} failures")
    return parsed_df, fail_df


def crosscheck_cagr(parsed_df: pd.DataFrame, db_path: str = DB_PATH) -> pd.DataFrame:
    if parsed_df.empty:
        return pd.DataFrame()
    engine = create_engine(f"sqlite:///{db_path}")
    fr = pd.read_sql(
        text(
            "SELECT company_id, year, revenue_cagr_3yr, revenue_cagr_5yr, "
            "revenue_cagr_10yr, pat_cagr_3yr, pat_cagr_5yr, pat_cagr_10yr "
            "FROM financial_ratios"
        ),
        engine,
    )
    engine.dispose()
    latest = fr.loc[fr.groupby("company_id")["year"].idxmax()]

    anomalies = []
    for _, r in parsed_df.iterrows():
        mapping = CAGR_MAP.get(r["metric_type"])
        if not mapping or r["period_years"] not in mapping:
            continue
        col = mapping[r["period_years"]]
        comp_rows = latest[latest["company_id"] == r["company_id"]]
        if comp_rows.empty or col not in comp_rows.columns:
            continue
        computed = comp_rows.iloc[0][col]
        if pd.isna(computed):
            continue
        if abs(computed - r["value_pct"]) > 5:
            anomalies.append(
                {
                    "company_id": int(r["company_id"]),
                    "metric_type": r["metric_type"],
                    "period_years": r["period_years"],
                    "parsed_pct": r["value_pct"],
                    "computed_pct": round(computed, 2),
                    "divergence_pct": round(abs(computed - r["value_pct"]), 2),
                }
            )

    out = pd.DataFrame(anomalies)
    out.to_csv(os.path.join(OUTPUT_DIR, "cagr_crosscheck.csv"), index=False)
    print(f"[NLP] CAGR cross-check: {len(out)} divergences > 5% flagged")
    return out


if __name__ == "__main__":
    parsed, _ = parse_analysis()
    crosscheck_cagr(parsed)
