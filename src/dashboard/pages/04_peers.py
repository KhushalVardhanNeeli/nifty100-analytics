"""04 Peers — peer-group dropdown, radar comparison and KPI table."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.radar import METRICS, _rank_within
from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Peers")

st.title("Peer Comparison")

groups = db.get_peer_groups()
if not groups:
    st.warning("No peer groups available.")
    st.stop()

group = st.selectbox("Peer group", groups)
peers = db.get_peers(group)
if peers.empty:
    st.warning("No companies in this group.")
    st.stop()

tickers = peers["ticker"].tolist()
ticker = st.selectbox("Company", tickers)

cid = db.resolve_ticker(ticker)
latest_year = db.get_latest_year()
fr = db._query("SELECT * FROM financial_ratios WHERE year = ?", params=[latest_year])
scores = db.get_composite_scores()
fr = fr.merge(scores[["company_id", "composite_score"]], on="company_id", how="left")

group_ids = set(peers["company_id"])
peers_data = fr[fr["company_id"].isin(group_ids)].copy()

labels = [m[3] for m in METRICS]
comp_vals, peer_avgs = [], []
for name, col, invert, _ in METRICS:
    if col not in peers_data.columns:
        comp_vals.append(0.0)
        peer_avgs.append(0.0)
        continue
    ranks = _rank_within(peers_data[col], invert)
    cv = ranks.get(cid)
    comp_vals.append(0.0 if cv is None or pd.isna(cv) else float(cv))
    valid = ranks[ranks.notna()]
    peer_avgs.append(float(valid.mean()) if not valid.empty else 0.0)

fig = go.Figure()
fig.add_trace(go.Scatterpolar(r=comp_vals, theta=labels, fill="toself", name=ticker))
fig.add_trace(
    go.Scatterpolar(
        r=peer_avgs,
        theta=labels,
        fill="none",
        line=dict(dash="dash", color="gray"),
        name=f"{group} avg",
    )
)
fig.update_layout(
    polar=dict(radialaxis=dict(range=[0, 100])),
    height=560,
    title=f"{ticker} vs {group} average (percentile ranks)",
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader(f"Companies in {group}")

table_rows = []
for _, p in peers.iterrows():
    pid = int(p["company_id"])
    row = fr[fr["company_id"] == pid]
    if row.empty:
        continue
    r = row.iloc[0]
    table_rows.append(
        {
            "Ticker": p["ticker"],
            "Company": p["company_name"],
            "Benchmark": "★" if p["is_benchmark"] else "",
            "ROE %": (
                round(r["return_on_equity_pct"], 1) if pd.notna(r["return_on_equity_pct"]) else None
            ),
            "ROCE %": (
                round(r["return_on_capital_employed_pct"], 1)
                if pd.notna(r["return_on_capital_employed_pct"])
                else None
            ),
            "NPM %": (
                round(r["net_profit_margin_pct"], 1)
                if pd.notna(r["net_profit_margin_pct"])
                else None
            ),
            "D/E": (round(r["debt_to_equity"], 2) if pd.notna(r["debt_to_equity"]) else None),
            "Composite": (
                round(r["composite_score"], 1) if pd.notna(r["composite_score"]) else None
            ),
        }
    )

tbl = pd.DataFrame(table_rows)
st.dataframe(tbl, use_container_width=True, hide_index=True)
st.caption("★ marks the benchmark company in the peer group.")
