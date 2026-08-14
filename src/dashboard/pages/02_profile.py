"""02 Company Profile — search a company, view KPIs, trends, pros & cons."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Profile")

st.title("Company Profile")

companies = db.get_companies()
if companies.empty:
    st.warning("No company data available.")
    st.stop()

companies["_label"] = companies["ticker"] + " — " + companies["company_name"]
selected = st.selectbox("Search company (name or ticker)", companies["_label"].tolist())
ticker = selected.split(" — ")[0]

cid = db.resolve_ticker(ticker)
if cid is None:
    st.error("Ticker not found — please try another.")
    st.stop()

comp = companies[companies["company_id"] == cid].iloc[0]
ratios = db.get_ratios(ticker)
pl = db.get_pl(ticker)
bs = db.get_bs(ticker)
cf = db.get_cf(ticker)
latest = ratios.sort_values("year").tail(1)

# ── Company card ────────────────────────────────────────────────────
st.markdown(f"### {comp['company_name']} ({comp['ticker']})")
meta = " · ".join(x for x in [
    comp.get("broad_sector"), comp.get("sub_sector"),
    comp.get("about_company") if pd.notna(comp.get("about_company")) else None,
] if x)
st.caption(meta or "—")

if not latest.empty:
    r = latest.iloc[0]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("ROE %", f"{r['return_on_equity_pct']:.1f}" if pd.notna(r['return_on_equity_pct']) else "N/A")
    c2.metric("ROCE %", f"{r['return_on_capital_employed_pct']:.1f}" if pd.notna(r['return_on_capital_employed_pct']) else "N/A")
    c3.metric("Net Profit Margin %", f"{r['net_profit_margin_pct']:.1f}" if pd.notna(r['net_profit_margin_pct']) else "N/A")
    c4.metric("D/E", f"{r['debt_to_equity']:.2f}" if pd.notna(r['debt_to_equity']) else "N/A")
    c5.metric("Revenue CAGR 5y", f"{r['revenue_cagr_5yr']:.1f}%" if pd.notna(r['revenue_cagr_5yr']) else "N/A")
    c6.metric("FCF (Cr)", f"{r['free_cash_flow_cr']:,.0f}" if pd.notna(r['free_cash_flow_cr']) else "N/A")

st.markdown("---")

# ── 10-year Revenue & Net Profit bar chart ──────────────────────────
if not pl.empty:
    st.subheader("Revenue and Net Profit (10-year)")
    pl_chart = pl.tail(10)[["year", "sales", "net_profit"]].melt(
        id_vars="year", var_name="Metric", value_name="Value")
    fig = px.bar(pl_chart, x="year", y="Value", color="Metric", barmode="group")
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

# ── ROE & ROCE dual-axis line ───────────────────────────────────────
if not ratios.empty:
    st.subheader("ROE and ROCE Trend")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ratios["year"], y=ratios["return_on_equity_pct"],
                             name="ROE %", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=ratios["year"], y=ratios["return_on_capital_employed_pct"],
                             name="ROCE %", mode="lines+markers", yaxis="y2"))
    fig.update_layout(height=380, yaxis=dict(title="ROE %"), yaxis2=dict(title="ROCE %", overlaying="y", side="right"))
    st.plotly_chart(fig, use_container_width=True)

# ── Pros & Cons badges ──────────────────────────────────────────────
pc = db.get_proscons(cid)
if not pc.empty:
    st.subheader("Pros & Cons")
    col_p, col_c = st.columns(2)
    with col_p:
        st.markdown("**Pros**")
        for pros in pc["pros"].dropna().unique()[:6]:
            st.markdown(f"- ✅ {pros}")
    with col_c:
        st.markdown("**Cons**")
        for cons in pc["cons"].dropna().unique()[:6]:
            st.markdown(f"- ❌ {cons}")
else:
    st.info("No pros/cons data available for this company.")
