"""08 Reports — annual-report PDF links per company (with 404 detection)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
import streamlit as st

from src.dashboard.utils import db

st.set_page_config(layout="wide", page_title="Nifty 100 Analytics — Reports")

st.title("Annual Reports")

companies = db.get_companies()
if companies.empty:
    st.warning("No data available.")
    st.stop()

companies["_label"] = companies["ticker"] + " — " + companies["company_name"]
selected = st.selectbox("Company", companies["_label"].tolist())
ticker = selected.split(" — ")[0]
cid = db.resolve_ticker(ticker)

docs = db.get_documents(cid)
if docs.empty:
    st.info("No annual reports found for this company.")
    st.stop()


@st.cache_data(ttl=3600)
def _url_status(url: str) -> str:
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        return "ok" if resp.status_code == 200 else f"error:{resp.status_code}"
    except Exception:
        return "unknown"


st.markdown(f"### Annual Reports — {ticker}")
for _, row in docs.iterrows():
    yr = int(row["year"]) if row["year"] is not None else "?"
    url = row["annual_report"]
    status = _url_status(url) if url else "missing"

    if status == "ok":
        st.markdown(f"**{yr}** — [Open PDF]({url})")
    elif status.startswith("error:404"):
        st.markdown(
            f"**{yr}** — <span style='color:red;font-weight:bold'>Report unavailable (404)</span>",
            unsafe_allow_html=True,
        )
    elif status == "unknown":
        st.markdown(f"**{yr}** — [Open PDF]({url}) ⚠️ (unverified)")
    else:
        st.markdown(
            f"**{yr}** — <span style='color:red'>Report unavailable</span>",
            unsafe_allow_html=True,
        )
