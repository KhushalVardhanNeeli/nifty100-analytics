"""07 Capital — capital-allocation treemap across the 8 patterns."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Capital")

st.title("Capital Allocation Map")

latest_year = db.get_latest_year()
fr = db._query("SELECT company_id, year, capital_allocation_pattern FROM financial_ratios "
               "WHERE year = ?", params=[latest_year])
companies = db.get_companies()

df = fr.merge(companies[["company_id", "ticker", "company_name", "broad_sector"]],
              on="company_id", how="left")
df["pattern"] = df["capital_allocation_pattern"].fillna("Unclassified")
df["size"] = 1

if df.empty:
    st.warning("No capital allocation data available.")
    st.stop()

st.subheader(f"Companies by Capital Allocation Pattern ({latest_year})")
fig = px.treemap(df, path=["pattern", "ticker"], values="size",
                 color="pattern", title="Capital Allocation Treemap")
fig.update_layout(height=640)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
pattern_counts = df["pattern"].value_counts()
selected_pattern = st.selectbox("Show companies in pattern", pattern_counts.index.tolist())
pattern_df = df[df["pattern"] == selected_pattern][["ticker", "company_name", "broad_sector"]]
st.markdown(f"**{len(pattern_df)} companies** in *{selected_pattern}*")
st.dataframe(pattern_df, use_container_width=True, hide_index=True)
