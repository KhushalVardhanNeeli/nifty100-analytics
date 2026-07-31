import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.screener.engine import ScreenerEngine

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "nifty100.db"
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "screener_config.yaml"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=300)
def query_db(query, params=None):
    conn = get_conn()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_companies():
    return query_db("SELECT * FROM companies")


@st.cache_data(ttl=300)
def get_sectors():
    return [row["sector_name"] for row in
            query_db("SELECT DISTINCT sector_name FROM companies WHERE sector_name IS NOT NULL ORDER BY sector_name")
            .itertuples(index=False)]


@st.cache_data(ttl=300)
def get_year_range():
    df = query_db("SELECT MIN(year) as min_year, MAX(year) as max_year FROM profitandloss")
    if df.empty:
        return None, None
    return int(df.iloc[0]["min_year"]), int(df.iloc[0]["max_year"])


@st.cache_data(ttl=300)
def get_financial_ratios_for_company(company_id):
    return query_db(
        "SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_profit_loss_for_company(company_id):
    return query_db(
        "SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_balance_sheet_for_company(company_id):
    return query_db(
        "SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_cashflow_for_company(company_id):
    return query_db(
        "SELECT * FROM cashflow WHERE company_id = ? ORDER BY year",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_stock_prices_for_company(company_id):
    df = query_db(
        "SELECT * FROM stock_prices WHERE company_id = ? ORDER BY trade_date",
        params=[company_id],
    )
    if not df.empty:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@st.cache_data(ttl=300)
def get_peer_percentiles_for_company(company_id):
    return query_db(
        """SELECT pp.metric_name, pp.percentile_rank, pp.peer_group, pp.year
           FROM peer_percentiles pp
           WHERE pp.company_id = ?
           ORDER BY pp.metric_name, pp.year""",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_pros_cons_for_company(company_id):
    return query_db(
        "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
        params=[company_id],
    )


@st.cache_data(ttl=300)
def get_market_cap_annual_for_company(company_id):
    return query_db(
        "SELECT * FROM market_cap_annual WHERE company_id = ? ORDER BY year",
        params=[company_id],
    )


# ── Page: Overview ────────────────────────────────────────────────────────

def page_overview():
    st.title("Nifty 100 Analytics — Overview")

    companies = get_companies()
    if companies.empty:
        st.warning("No data available in the database.")
        return

    total_companies = len(companies)
    sectors = companies["sector_name"].dropna().unique()
    total_sectors = len(sectors)
    min_year, max_year = get_year_range()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Companies", total_companies)
    col2.metric("Sectors", total_sectors)
    col3.metric("Data From", f"{min_year}" if min_year else "N/A")
    col4.metric("Data To", f"{max_year}" if max_year else "N/A")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Companies by Sector")
        sector_counts = companies["sector_name"].value_counts().reset_index()
        sector_counts.columns = ["Sector", "Count"]
        fig = px.bar(
            sector_counts,
            x="Sector",
            y="Count",
            color="Sector",
            title="Sector Breakdown",
        )
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Market Cap Distribution")
        mc_data = companies[companies["market_cap"].notna() & (companies["market_cap"] > 0)].copy()
        if not mc_data.empty:
            mc_data["market_cap_log"] = np.log10(mc_data["market_cap"])
            fig = px.histogram(
                mc_data,
                x="market_cap_log",
                nbins=30,
                title="Market Cap Distribution (Log10 Scale)",
                labels={"market_cap_log": "Log10(Market Cap)"},
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No market cap data available.")

    st.markdown("---")
    st.subheader("Top 10 Companies by Market Cap")

    top10 = companies[companies["market_cap"].notna()].nlargest(10, "market_cap")
    if not top10.empty:
        top10_display = top10[["ticker", "company_name", "sector_name", "market_cap"]].copy()
        top10_display["market_cap"] = top10_display["market_cap"].apply(
            lambda x: f"₹{x:,.0f} Cr" if pd.notna(x) else "N/A"
        )
        top10_display.index = range(1, len(top10_display) + 1)
        st.dataframe(top10_display, use_container_width=True)

        fig = px.bar(
            top10,
            x="ticker",
            y="market_cap",
            color="sector_name",
            title="Top 10 by Market Cap",
            labels={"market_cap": "Market Cap (Cr)", "ticker": "Ticker"},
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No market cap data available.")


# ── Page: Company Explorer ────────────────────────────────────────────────

def page_company_explorer():
    st.title("Company Explorer")

    companies = get_companies()
    if companies.empty:
        st.warning("No companies found.")
        return

    company_names = companies["company_name"].dropna().sort_values().tolist()
    selected_name = st.sidebar.selectbox("Select Company", company_names, key="company_select")

    if not selected_name:
        st.info("Select a company from the sidebar.")
        return

    company = companies[companies["company_name"] == selected_name].iloc[0]
    company_id = int(company["company_id"])
    ticker = company["ticker"]
    sector = company["sector_name"] or "N/A"
    market_cap = company["market_cap"] or 0

    st.header(f"{ticker} — {selected_name}")
    st.caption(f"Sector: {sector} | Market Cap: ₹{market_cap:,.0f} Cr" if market_cap else f"Sector: {sector}")

    pros_cons_df = get_pros_cons_for_company(company_id)
    if not pros_cons_df.empty:
        row = pros_cons_df.iloc[0]
        col_p, col_c = st.columns(2)
        with col_p:
            if row["pros"] and pd.notna(row["pros"]):
                st.info(f"**Pros:** {row['pros']}")
        with col_c:
            if row["cons"] and pd.notna(row["cons"]):
                st.warning(f"**Cons:** {row['cons']}")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Financial Ratios", "P&L", "Balance Sheet", "Cash Flow", "Stock Price"
    ])

    with tab1:
        st.subheader("Financial Ratios Over Time")
        ratios_df = get_financial_ratios_for_company(company_id)
        if not ratios_df.empty:
            ratio_metrics = [
                "roe", "roce", "roa", "net_profit_margin", "operating_profit_margin",
                "debt_to_equity", "interest_coverage", "asset_turnover",
                "current_ratio", "quick_ratio", "dividend_yield", "fcf_yield",
                "pe_ratio", "pb_ratio",
            ]
            available_metrics = [m for m in ratio_metrics if m in ratios_df.columns]
            selected_metrics = st.multiselect(
                "Select ratios to plot",
                available_metrics,
                default=[m for m in ["roe", "roce", "net_profit_margin", "debt_to_equity"]
                         if m in available_metrics],
            )
            if selected_metrics:
                fig = go.Figure()
                for metric in selected_metrics:
                    valid = ratios_df[ratios_df[metric].notna()]
                    if not valid.empty:
                        fig.add_trace(go.Scatter(
                            x=valid["year"],
                            y=valid[metric],
                            mode="lines+markers",
                            name=metric.replace("_", " ").title(),
                        ))
                fig.update_layout(
                    xaxis_title="Year",
                    yaxis_title="Value",
                    height=500,
                    hovermode="x unified",
                )
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Latest Ratios")
            latest = ratios_df[ratios_df["year"] == ratios_df["year"].max()]
            if not latest.empty:
                cols = st.columns(4)
                latest_row = latest.iloc[0]
                for i, metric in enumerate(["roe", "roce", "roa", "net_profit_margin",
                                             "operating_profit_margin", "debt_to_equity",
                                             "interest_coverage", "dividend_yield"]):
                    if metric in latest_row.index:
                        val = latest_row[metric]
                        display = f"{val:.2f}" if pd.notna(val) else "N/A"
                        if metric in ("roe", "roce", "roa", "net_profit_margin",
                                      "operating_profit_margin", "dividend_yield"):
                            display = f"{display}%" if pd.notna(val) else "N/A"
                        cols[i % 4].metric(
                            label=metric.replace("_", " ").title(),
                            value=display,
                        )
        else:
            st.info("No financial ratios available.")

    with tab2:
        st.subheader("Profit & Loss")
        pl_df = get_profit_loss_for_company(company_id)
        if not pl_df.empty:
            numeric_cols = pl_df.select_dtypes(include=["float64", "int64"]).columns.tolist()
            pl_display = pl_df[["year"] + [c for c in numeric_cols if c != "company_id" and c != "pnl_id"]]
            st.dataframe(pl_display, use_container_width=True, hide_index=True)

            st.subheader("Revenue & Profit Trend")
            plot_cols = [c for c in ["total_revenue", "sales", "net_profit", "cogs"] if c in pl_df.columns]
            if plot_cols:
                fig = go.Figure()
                for col in plot_cols:
                    valid = pl_df[pl_df[col].notna()]
                    if not valid.empty:
                        fig.add_trace(go.Bar(
                            x=valid["year"], y=valid[col],
                            name=col.replace("_", " ").title(),
                        ))
                fig.update_layout(
                    barmode="group",
                    height=400,
                    xaxis_title="Year",
                    yaxis_title="Amount",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No P&L data available.")

    with tab3:
        st.subheader("Balance Sheet")
        bs_df = get_balance_sheet_for_company(company_id)
        if not bs_df.empty:
            numeric_cols = bs_df.select_dtypes(include=["float64", "int64"]).columns.tolist()
            bs_display = bs_df[["year"] + [c for c in numeric_cols if c not in ("company_id", "bs_id")]]
            st.dataframe(bs_display, use_container_width=True, hide_index=True)

            st.subheader("Assets vs Liabilities")
            plot_cols = [c for c in ["total_assets", "total_liabilities", "shareholders_equity",
                                      "total_debt", "cash_and_equivalents"] if c in bs_df.columns]
            if plot_cols:
                fig = go.Figure()
                for col in plot_cols:
                    valid = bs_df[bs_df[col].notna()]
                    if not valid.empty:
                        fig.add_trace(go.Bar(
                            x=valid["year"], y=valid[col],
                            name=col.replace("_", " ").title(),
                        ))
                fig.update_layout(
                    barmode="group",
                    height=400,
                    xaxis_title="Year",
                    yaxis_title="Amount",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No balance sheet data available.")

    with tab4:
        st.subheader("Cash Flow")
        cf_df = get_cashflow_for_company(company_id)
        if not cf_df.empty:
            numeric_cols = cf_df.select_dtypes(include=["float64", "int64"]).columns.tolist()
            cf_display = cf_df[["year"] + [c for c in numeric_cols if c not in ("company_id", "cf_id")]]
            st.dataframe(cf_display, use_container_width=True, hide_index=True)

            st.subheader("Cash Flow Components")
            plot_cols = [c for c in ["operating_activities", "investing_activities",
                                      "financing_activities", "fcf"] if c in cf_df.columns]
            if plot_cols:
                fig = go.Figure()
                for col in plot_cols:
                    valid = cf_df[cf_df[col].notna()]
                    if not valid.empty:
                        fig.add_trace(go.Bar(
                            x=valid["year"], y=valid[col],
                            name=col.replace("_", " ").title(),
                        ))
                fig.update_layout(
                    barmode="group",
                    height=400,
                    xaxis_title="Year",
                    yaxis_title="Amount",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No cash flow data available.")

    with tab5:
        st.subheader("Stock Price")
        sp_df = get_stock_prices_for_company(company_id)
        if not sp_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Latest Close", f"₹{sp_df.iloc[-1]['close']:.2f}")
            with col2:
                if len(sp_df) > 1:
                    change = sp_df.iloc[-1]["close"] - sp_df.iloc[-2]["close"]
                    pct_change = (change / sp_df.iloc[-2]["close"]) * 100
                    st.metric("Last Change", f"₹{change:+.2f}", f"{pct_change:+.2f}%")

            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=sp_df["trade_date"],
                open=sp_df["open"],
                high=sp_df["high"],
                low=sp_df["low"],
                close=sp_df["close"],
                name="Price",
            ))
            fig.add_trace(go.Bar(
                x=sp_df["trade_date"],
                y=sp_df["volume"],
                name="Volume",
                yaxis="y2",
                marker_color="lightgray",
                opacity=0.5,
            ))
            fig.update_layout(
                height=500,
                yaxis=dict(title="Price (₹)"),
                yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
                xaxis=dict(title="Date"),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Stock Price Data")
            sp_display = sp_df[["trade_date", "open", "high", "low", "close", "volume"]].copy()
            sp_display["trade_date"] = sp_display["trade_date"].dt.strftime("%Y-%m-%d")
            st.dataframe(sp_display, use_container_width=True, hide_index=True)
        else:
            st.info("No stock price data available.")


# ── Page: Screener ────────────────────────────────────────────────────────

PRESET_NAMES = [
    "Quality_Compounder", "Value_Pick", "Growth_Accelerator",
    "Dividend_Champion", "Debt_Free_Blue_Chip", "Turnaround_Watch",
]

PRESET_LABELS = {
    "Quality_Compounder": "Quality Compounder",
    "Value_Pick": "Value Pick",
    "Growth_Accelerator": "Growth Accelerator",
    "Dividend_Champion": "Dividend Champion",
    "Debt_Free_Blue_Chip": "Debt-Free Blue Chip",
    "Turnaround_Watch": "Turnaround Watch",
}

PRESET_DESCRIPTIONS = {
    "Quality_Compounder": "Companies with high ROE, consistent revenue growth, and strong cash flows",
    "Value_Pick": "Undervalued companies with reasonable fundamentals",
    "Growth_Accelerator": "High-growth companies with strong revenue and profit momentum",
    "Dividend_Champion": "Consistent dividend payers with strong balance sheets",
    "Debt_Free_Blue_Chip": "Companies with zero or near-zero debt and strong fundamentals",
    "Turnaround_Watch": "Companies showing early signs of operational recovery",
}


def page_screener():
    st.title("Stock Screener")

    try:
        engine = ScreenerEngine(config_path=str(CONFIG_PATH), db_path=str(DB_PATH))
    except Exception as e:
        st.error(f"Failed to initialize screener engine: {e}")
        return

    st.markdown("Select an investment preset to screen Nifty 100 companies based on financial criteria.")

    preset_options = [PRESET_LABELS[p] for p in PRESET_NAMES]
    selected_label = st.selectbox("Choose Preset", preset_options)

    selected_preset = [k for k, v in PRESET_LABELS.items() if v == selected_label]
    if not selected_preset:
        return
    selected_preset = selected_preset[0]

    st.caption(f"*{PRESET_DESCRIPTIONS[selected_preset]}*")

    if st.button("Run Screen", type="primary", use_container_width=True):
        with st.spinner(f"Running {selected_label} screen..."):
            try:
                result = engine.screen(selected_preset)
            except Exception as e:
                st.error(f"Screening failed: {e}")
                return

        if result.empty:
            st.warning(f"No companies passed the {selected_label} filters.")
            return

        st.success(f"Found {len(result)} companies matching '{selected_label}' criteria.")

        display_cols = [
            "ticker", "company_name", "sector_name", "market_cap",
            "roe", "net_profit_margin", "debt_to_equity",
            "revenue_cagr_3y", "composite_score",
        ]
        available_cols = [c for c in display_cols if c in result.columns]
        display_df = result[available_cols].copy()
        for col in display_df.select_dtypes(include=["float64", "float32"]).columns:
            display_df[col] = display_df[col].apply(lambda x: round(x, 2) if pd.notna(x) else x)

        st.dataframe(
            display_df.rename(columns={
                "roe": "ROE (%)",
                "net_profit_margin": "NPM (%)",
                "debt_to_equity": "D/E",
                "revenue_cagr_3y": "Rev CAGR 3Y (%)",
                "composite_score": "Score",
            }),
            use_container_width=True,
            hide_index=True,
        )

        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download as CSV",
            data=csv,
            file_name=f"{selected_preset}_results.csv",
            mime="text/csv",
        )


# ── Page: Peer Comparison ─────────────────────────────────────────────────

def page_peer_comparison():
    st.title("Peer Comparison")

    companies = get_companies()
    if companies.empty:
        st.warning("No companies found.")
        return

    company_names = companies["company_name"].dropna().sort_values().tolist()
    selected_name = st.sidebar.selectbox(
        "Select Company", company_names, key="peer_company_select"
    )

    if not selected_name:
        st.info("Select a company from the sidebar.")
        return

    company = companies[companies["company_name"] == selected_name].iloc[0]
    company_id = int(company["company_id"])
    ticker = company["ticker"]
    peer_group = company.get("sector_name") or "Others"

    st.header(f"{ticker} — {selected_name}")
    st.caption(f"Peer Group: {peer_group}")

    pp_df = get_peer_percentiles_for_company(company_id)

    if pp_df.empty:
        st.info("No peer percentile data available for this company.")
        return

    latest_year = pp_df["year"].max()
    latest_pp = pp_df[pp_df["year"] == latest_year]

    if latest_pp.empty:
        st.info(f"No peer data for the latest year ({latest_year}).")
        return

    st.subheader(f"Percentile Ranks vs Peers (Year: {latest_year})")

    metrics = latest_pp["metric_name"].unique().tolist()
    metric_display_options = [m.replace("_", " ").title() for m in metrics]

    selected_metric_display = st.selectbox("Select Metric", metric_display_options)
    selected_metric = metrics[metric_display_options.index(selected_metric_display)]

    selected_pct = latest_pp[latest_pp["metric_name"] == selected_metric]
    if selected_pct.empty:
        st.info(f"No data for metric '{selected_metric}'.")
        return

    pct_value = selected_pct.iloc[0]["percentile_rank"]

    if pd.notna(pct_value):
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=pct_value,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": f"Peer Percentile — {selected_metric_display}"},
            delta={"reference": 50},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "darkblue"},
                "steps": [
                    {"range": [0, 25], "color": "#FFC7CE"},
                    {"range": [25, 50], "color": "#FFEB9C"},
                    {"range": [50, 75], "color": "#BDD7EE"},
                    {"range": [75, 100], "color": "#C6EFCE"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.75,
                    "value": 50,
                },
            },
        ))
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

        if pct_value >= 75:
            st.success(f"Top quartile ({pct_value:.1f}th percentile)")
        elif pct_value >= 50:
            st.info(f"Above median ({pct_value:.1f}th percentile)")
        elif pct_value >= 25:
            st.warning(f"Below median ({pct_value:.1f}th percentile)")
        else:
            st.error(f"Bottom quartile ({pct_value:.1f}th percentile)")
    else:
        st.info("Percentile data not available for this metric.")

    st.markdown("---")
    st.subheader(f"All Percentile Ranks (Year: {latest_year})")

    all_data = latest_pp[["metric_name", "percentile_rank"]].copy()
    all_data["metric_name"] = all_data["metric_name"].str.replace("_", " ").str.title()
    all_data["percentile_rank"] = all_data["percentile_rank"].apply(
        lambda x: f"{x:.1f}" if pd.notna(x) else "N/A"
    )

    def color_pct(val):
        try:
            v = float(val)
            if v >= 75:
                return "background-color: #C6EFCE"
            elif v >= 50:
                return "background-color: #BDD7EE"
            elif v >= 25:
                return "background-color: #FFEB9C"
            else:
                return "background-color: #FFC7CE"
        except (ValueError, TypeError):
            return ""

    styled = all_data.style.map(color_pct, subset=["percentile_rank"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Page: Sector View ─────────────────────────────────────────────────────

def page_sector_view():
    st.title("Sector View")

    sectors = get_sectors()
    if not sectors:
        st.warning("No sectors found.")
        return

    selected_sector = st.sidebar.selectbox("Select Sector", sectors, key="sector_select")

    if not selected_sector:
        return

    st.header(f"Sector: {selected_sector}")

    companies = get_companies()
    sector_companies = companies[companies["sector_name"] == selected_sector]
    sector_company_ids = sector_companies["company_id"].tolist()

    st.metric("Companies in Sector", len(sector_company_ids))

    if not sector_company_ids:
        st.info("No companies in this sector.")
        return

    ratios_df = query_db(
        f"""SELECT fr.*, c.ticker, c.company_name
            FROM financial_ratios fr
            JOIN companies c ON fr.company_id = c.company_id
            WHERE fr.company_id IN ({','.join('?' * len(sector_company_ids))})
            ORDER BY fr.year""",
        params=sector_company_ids,
    )

    if ratios_df.empty:
        st.info("No financial ratio data for this sector.")
        return

    latest_year = ratios_df["year"].max()
    latest_data = ratios_df[ratios_df["year"] == latest_year]

    st.markdown("---")
    st.subheader(f"Aggregate Metrics (Year: {latest_year})")

    agg_metrics = [
        "roe", "roce", "roa", "net_profit_margin", "operating_profit_margin",
        "gross_profit_margin", "debt_to_equity", "interest_coverage",
        "asset_turnover", "current_ratio", "quick_ratio",
        "dividend_yield", "fcf_yield", "pe_ratio", "pb_ratio",
    ]
    available_metrics = [m for m in agg_metrics if m in latest_data.columns]

    if available_metrics:
        agg_values = {}
        for metric in available_metrics:
            series = latest_data[metric].dropna()
            if len(series) > 0:
                agg_values[metric.replace("_", " ").title()] = series

        col1, col2, col3 = st.columns(3)
        for i, (label, series) in enumerate(agg_values.items()):
            mean_val = series.mean()
            median_val = series.median()
            count = len(series)
            target_col = [col1, col2, col3][i % 3]
            target_col.metric(
                label=label,
                value=f"μ={mean_val:.2f}",
                delta=f"Median={median_val:.2f} (n={count})",
            )

    st.markdown("---")
    st.subheader("Company-wise Comparison")

    metric_display = [m.replace("_", " ").title() for m in available_metrics]
    selected_metric_display = st.selectbox("Select Metric", metric_display)
    selected_metric = available_metrics[metric_display.index(selected_metric_display)]

    comp_df = latest_data[["ticker", "company_name", selected_metric]].dropna()
    comp_df = comp_df.sort_values(selected_metric, ascending=False)

    if not comp_df.empty:
        colors = px.colors.qualitative.Plotly
        fig = px.bar(
            comp_df,
            x="ticker",
            y=selected_metric,
            color="ticker",
            title=f"{selected_metric.replace('_', ' ').title()} by Company in {selected_sector}",
            labels={selected_metric: selected_metric.replace("_", " ").title()},
            color_discrete_sequence=colors * (len(comp_df) // len(colors) + 1),
        )
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            comp_df.rename(columns={selected_metric: selected_metric.replace("_", " ").title()}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.subheader("Historical Sector Trend")

    trend_metrics_display = [m.replace("_", " ").title() for m in available_metrics]
    selected_trend_display = st.selectbox(
        "Select Trend Metric", trend_metrics_display, key="trend_metric"
    )
    selected_trend_metric = available_metrics[trend_metrics_display.index(selected_trend_display)]

    yearly_agg = ratios_df.groupby("year")[selected_trend_metric].agg(["mean", "median"]).reset_index()
    yearly_agg = yearly_agg.dropna()

    if not yearly_agg.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=yearly_agg["year"],
            y=yearly_agg["mean"],
            mode="lines+markers",
            name="Mean",
            line=dict(width=2),
        ))
        fig.add_trace(go.Scatter(
            x=yearly_agg["year"],
            y=yearly_agg["median"],
            mode="lines+markers",
            name="Median",
            line=dict(dash="dash", width=2),
        ))
        fig.update_layout(
            title=f"Sector {selected_trend_metric.replace('_', ' ').title()} Trend",
            xaxis_title="Year",
            yaxis_title=selected_trend_metric.replace("_", " ").title(),
            height=400,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Companies in Sector")
    sector_display = sector_companies[["ticker", "company_name", "market_cap"]].copy()
    sector_display["market_cap"] = sector_display["market_cap"].apply(
        lambda x: f"₹{x:,.0f} Cr" if pd.notna(x) else "N/A"
    )
    st.dataframe(sector_display, use_container_width=True, hide_index=True)


# ── Main App ──────────────────────────────────────────────────────────────

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        ["Overview", "Company Explorer", "Screener", "Peer Comparison", "Sector View"],
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("Nifty 100 Analytics Dashboard")
    st.sidebar.caption("Data from Nifty 100 companies")

    pages = {
        "Overview": page_overview,
        "Company Explorer": page_company_explorer,
        "Screener": page_screener,
        "Peer Comparison": page_peer_comparison,
        "Sector View": page_sector_view,
    }

    try:
        pages[page]()
    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
