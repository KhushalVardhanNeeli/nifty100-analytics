"""03 Screener — 6 presets + custom slider filters with live CSV export."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.dashboard.utils import db
from src.screener.engine import ScreenerEngine

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Screener")

st.title("Screener")

DEFAULTS = {
    "roe": 0,
    "de": 5,
    "fcf": -1000,
    "rev": -50,
    "pat": -50,
    "opm": -50,
    "pe": 200,
    "pb": 30,
    "dy": 0,
    "icr": 0,
}

PRESET_SLIDERS = {
    "Quality_Compounder": {"roe": 15, "de": 1, "fcf": 0, "rev": 10},
    "Value_Pick": {"pe": 35, "pb": 5, "de": 2, "dy": 1},
    "Growth_Accelerator": {"pat": 20, "rev": 15, "de": 2},
    "Dividend_Champion": {"dy": 2},
    "Debt_Free_Blue_Chip": {"de": 0, "roe": 12},
    "Turnaround_Watch": {"rev": 10, "fcf": 0},
}

st.sidebar.markdown("### Presets")
for name, vals in PRESET_SLIDERS.items():
    if st.sidebar.button(name.replace("_", " "), key=f"preset_{name}", use_container_width=True):
        for k, v in vals.items():
            st.session_state[k] = v

st.sidebar.markdown("### Thresholds")
roe = st.sidebar.slider("ROE min %", 0, 60, int(st.session_state.get("roe", DEFAULTS["roe"])))
de = st.sidebar.slider("D/E max", 0.0, 5.0, float(st.session_state.get("de", DEFAULTS["de"])))
fcf = st.sidebar.slider(
    "FCF min (Cr)",
    -2000.0,
    10000.0,
    float(st.session_state.get("fcf", DEFAULTS["fcf"])),
)
rev = st.sidebar.slider(
    "Revenue CAGR 5y min %",
    -50.0,
    60.0,
    float(st.session_state.get("rev", DEFAULTS["rev"])),
)
pat = st.sidebar.slider(
    "PAT CAGR 5y min %",
    -50.0,
    60.0,
    float(st.session_state.get("pat", DEFAULTS["pat"])),
)
opm = st.sidebar.slider(
    "OPM min %", -50.0, 60.0, float(st.session_state.get("opm", DEFAULTS["opm"]))
)
pe = st.sidebar.slider("P/E max", 5.0, 200.0, float(st.session_state.get("pe", DEFAULTS["pe"])))
pb = st.sidebar.slider("P/B max", 0.0, 30.0, float(st.session_state.get("pb", DEFAULTS["pb"])))
dy = st.sidebar.slider(
    "Dividend Yield min %", 0.0, 6.0, float(st.session_state.get("dy", DEFAULTS["dy"]))
)
icr = st.sidebar.slider(
    "Interest Coverage min",
    0.0,
    15.0,
    float(st.session_state.get("icr", DEFAULTS["icr"])),
)


@st.cache_data(ttl=600)
def _load_screener_data():
    return ScreenerEngine(db_path=str(db.DB_PATH)).load_data()


df = _load_screener_data()
if df.empty:
    st.warning("No screener data available.")
    st.stop()

is_fin = df["broad_sector"].fillna("").astype(str).str.lower().str.contains("financial")

mask = (
    (df["roe"].fillna(-999) >= roe)
    & ((df["debt_to_equity"].fillna(999) <= de) | is_fin)  # D/E skips Financials
    & (df["free_cash_flow"].fillna(-1e18) >= fcf)
    & (df["revenue_cagr_5y"].fillna(-1e18) >= rev)
    & (df["pat_cagr_5y"].fillna(-1e18) >= pat)
    & (df["operating_profit_margin"].fillna(-1e18) >= opm)
    & (df["pe_ratio"].fillna(1e9) <= pe)
    & (df["pb_ratio"].fillna(1e9) <= pb)
    & (df["dividend_yield"].fillna(-1) >= dy)
    & ((df["interest_coverage"].fillna(-1) >= icr) | (df["icr_label"].eq("Debt Free")))
)

result = df[mask].copy()
result = (
    result.sort_values("composite_score", ascending=False)
    if "composite_score" in result
    else result
)

cols = [
    "ticker",
    "company_name",
    "broad_sector",
    "roe",
    "roce",
    "net_profit_margin",
    "debt_to_equity",
    "interest_coverage",
    "free_cash_flow",
    "revenue_cagr_5y",
    "pat_cagr_5y",
    "pe_ratio",
    "pb_ratio",
    "dividend_yield",
    "composite_score",
]
cols = [c for c in cols if c in result.columns]

st.markdown(f"### {len(result)} companies match your filters")
st.dataframe(
    result[cols].round(2) if not result.empty else result,
    use_container_width=True,
    hide_index=True,
)

csv = result[cols].to_csv(index=False).encode("utf-8")
st.download_button("Download CSV", csv, file_name="screener_results.csv", mime="text/csv")
