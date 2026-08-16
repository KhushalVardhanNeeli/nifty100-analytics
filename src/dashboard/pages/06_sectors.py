"""06 Sectors — sector bubble chart and median KPI comparison."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Sectors")

st.title("Sector Analysis")

sectors = db.get_sectors()
if not sectors:
    st.warning("No sector data available.")
    st.stop()

sector = st.selectbox("Sector", sectors)
latest_year = db.get_latest_year()

fr = db._query("SELECT * FROM financial_ratios WHERE year = ?", params=[latest_year])
companies = db.get_companies()
pl = db._query("SELECT company_id, sales FROM profitandloss WHERE year = ?", params=[latest_year])
mc = db.get_market_cap_for_year(latest_year)

df = (fr.merge(companies[["company_id", "ticker", "company_name", "broad_sector", "sub_sector"]],
               on="company_id", how="left")
        .merge(pl, on="company_id", how="left")
        .merge(mc[["company_id", "market_cap_crore"]], on="company_id", how="left"))

sector_df = df[df["broad_sector"] == sector].copy()

if sector_df.empty:
    st.info(f"No companies found in {sector}.")
    st.stop()

st.subheader(f"{sector} — Bubble Chart ({latest_year})")
bubble = sector_df.dropna(subset=["sales", "return_on_equity_pct"])
if not bubble.empty:
    fig = px.scatter(bubble, x="sales", y="return_on_equity_pct",
                     size="market_cap_crore", color="sub_sector",
                     hover_name="ticker",
                     labels={"sales": "Revenue (Cr)", "return_on_equity_pct": "ROE %",
                             "market_cap_crore": "Market Cap (Cr)"})
    fig.update_layout(height=520)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough data for the bubble chart.")

st.markdown("---")
st.subheader("Sector Median KPIs")
median_cols = ["return_on_equity_pct", "return_on_capital_employed_pct",
               "net_profit_margin_pct", "debt_to_equity", "asset_turnover"]
rows = []
for sector_name in sectors:
    sub = df[df["broad_sector"] == sector_name]
    if sub.empty:
        continue
    rows.append({"Sector": sector_name,
                 **{c: sub[c].median() for c in median_cols if c in sub.columns}})
med = pd.DataFrame(rows)
st.dataframe(med.round(2), use_container_width=True, hide_index=True)
