"""01 Home — market-wide KPIs, sector donut, top-5 composite scores."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.express as px
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Home")

st.title("Home")
min_yr, max_yr = db.get_year_range()
year = st.sidebar.selectbox("Year", list(range(max_yr, min_yr - 1, -1)), index=0)

companies = db.get_companies()
ratios = db._query("SELECT * FROM financial_ratios WHERE year = ?", params=[int(year)])
mc = db.get_market_cap_for_year(year)

if companies.empty:
    st.warning("No data available in the database.")
    st.stop()

# ── 6 KPI tiles ─────────────────────────────────────────────────────
debt_free = int((ratios["debt_to_equity"] == 0).sum()) if not ratios.empty else 0
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Companies", len(companies))
c2.metric(
    "Average ROE %",
    f"{ratios['return_on_equity_pct'].mean():.1f}" if not ratios.empty else "N/A",
)
c3.metric("Median P/E", f"{mc['pe_ratio'].median():.1f}" if not mc.empty else "N/A")
c4.metric(
    "Median D/E",
    f"{ratios['debt_to_equity'].median():.2f}" if not ratios.empty else "N/A",
)
c5.metric(
    "Median Rev CAGR 5y",
    f"{ratios['revenue_cagr_5yr'].median():.1f}%" if not ratios.empty else "N/A",
)
c6.metric("Debt-Free Companies", debt_free)

st.markdown("---")

# ── Sector donut + top-5 composite ──────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader(f"Sector Breakdown ({year})")
    sector_counts = companies["broad_sector"].dropna().value_counts().reset_index()
    sector_counts.columns = ["Sector", "Count"]
    if not sector_counts.empty:
        fig = px.pie(sector_counts, names="Sector", values="Count", hole=0.45)
        fig.update_layout(height=420, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Top 5 Companies by Composite Score")
    scores = db.get_composite_scores()
    if not scores.empty:
        top5 = scores.nlargest(5, "composite_score")
        top5 = top5.merge(
            companies[["company_id", "company_name", "broad_sector"]],
            on="company_id",
            how="left",
        )
        st.dataframe(
            top5[["ticker", "company_name", "broad_sector", "composite_score"]].assign(
                composite_score=lambda d: d["composite_score"].round(1)
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Composite scores unavailable.")
