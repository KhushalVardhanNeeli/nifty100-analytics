"""05 Trends — multi-metric 10-year trend lines with YoY annotations."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Trends")

st.title("Trend Analysis")

companies = db.get_companies()
if companies.empty:
    st.warning("No data available.")
    st.stop()

companies["_label"] = companies["ticker"] + " — " + companies["company_name"]
selected = st.selectbox("Company", companies["_label"].tolist())
ticker = selected.split(" — ")[0]
cid = db.resolve_ticker(ticker)

pl = db.get_pl(ticker)
ratios = db.get_ratios(ticker)

if pl.empty:
    st.warning("No P&L data for this company.")
    st.stop()

data = pl[["year", "sales", "net_profit", "operating_profit", "eps"]].copy()
if not ratios.empty:
    data = data.merge(
        ratios[["year", "return_on_equity_pct", "return_on_capital_employed_pct",
                "net_profit_margin_pct", "debt_to_equity", "free_cash_flow_cr"]],
        on="year", how="left")

metric_labels = {
    "sales": "Sales (Cr)", "net_profit": "Net Profit (Cr)",
    "operating_profit": "Operating Profit (Cr)", "eps": "EPS (₹)",
    "return_on_equity_pct": "ROE %", "return_on_capital_employed_pct": "ROCE %",
    "net_profit_margin_pct": "Net Profit Margin %", "debt_to_equity": "D/E",
    "free_cash_flow_cr": "Free Cash Flow (Cr)",
}
metrics = st.multiselect("Select up to 3 metrics", list(metric_labels.keys()),
                         default=["sales", "net_profit"], max_selections=3)
data = data[["year"] + metrics]

if not metrics:
    st.info("Select at least one metric.")
    st.stop()

fig = go.Figure()
for m in metrics:
    s = data[["year", m]].dropna()
    if s.empty:
        continue
    s["yoy"] = s[m].pct_change() * 100
    fig.add_trace(go.Scatter(x=s["year"], y=s[m], name=metric_labels[m], mode="lines+markers"))
    for _, r in s.iterrows():
        if pd.notna(r["yoy"]):
            fig.add_annotation(x=r["year"], y=r[m], text=f"{r['yoy']:.0f}%",
                               showarrow=False, font=dict(size=9), yshift=12)

fig.update_layout(height=520, title=f"{ticker} — 10-year trends (YoY % shown)")
st.plotly_chart(fig, use_container_width=True)
