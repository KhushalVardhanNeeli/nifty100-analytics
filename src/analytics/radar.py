"""Radar charts — Sprint 3.

8-axis polar chart per company: ROE, ROCE, Net Profit Margin, D/E (inverted),
FCF, PAT CAGR 5y, Revenue CAGR 5y, Composite Score. Company polygon is
overlaid on the peer-group average (dashed). Companies without a peer group
get a single-metric standalone chart vs the Nifty 100 average.
"""

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

METRICS = [
    ("roe", "return_on_equity_pct", False, "ROE"),
    ("roce", "return_on_capital_employed_pct", False, "ROCE"),
    ("net_profit_margin", "net_profit_margin_pct", False, "Net Profit Margin"),
    ("debt_to_equity", "debt_to_equity", True, "D/E (inv)"),
    ("fcf", "free_cash_flow_cr", False, "FCF"),
    ("pat_cagr_5y", "pat_cagr_5yr", False, "PAT CAGR 5y"),
    ("revenue_cagr_5y", "revenue_cagr_5yr", False, "Rev CAGR 5y"),
    ("composite_score", "composite_score", False, "Composite Score"),
]


def _rank_within(values: pd.Series, invert: bool = False) -> pd.Series:
    s = values.dropna()
    if len(s) < 2:
        return pd.Series(np.nan, index=values.index)
    pct = s.rank(pct=True) * 100
    if invert:
        pct = 100 - pct
    return pct.reindex(values.index)


_composite_cache: dict = {}


def _load_composite(db_path: str) -> dict:
    if db_path in _composite_cache:
        return _composite_cache[db_path]
    from src.screener.engine import ScreenerEngine

    eng = ScreenerEngine(db_path=db_path)
    df = eng.load_data()
    df = eng.composite_score(df)
    result = {
        int(k): (None if pd.isna(v) else float(v))
        for k, v in zip(df["company_id"], df["composite_score"])
    }
    _composite_cache[db_path] = result
    return result


def _load_latest(db_path: str):
    conn = sqlite3.connect(db_path)
    year = int(pd.read_sql("SELECT MAX(year) AS y FROM financial_ratios", conn).iloc[0]["y"])
    fr = pd.read_sql("SELECT * FROM financial_ratios WHERE year = ?", conn, params=[year])
    groups = pd.read_sql("SELECT company_id, peer_group_name FROM peer_groups", conn)
    companies = pd.read_sql(
        "SELECT company_id, ticker, company_name, broad_sector FROM companies", conn
    )
    conn.close()
    return year, fr, groups, companies


def generate_radar(
    company_id: int, year: int, db_path: str, output_dir="reports/radar_charts/"
) -> str:
    year, fr, groups, companies = _load_latest(db_path)
    comp = companies[companies["company_id"] == company_id]
    if comp.empty or fr.empty:
        raise ValueError(f"Company {company_id} not found")
    ticker = comp.iloc[0]["ticker"]
    composite_map = _load_composite(db_path)
    fr = fr.copy()
    fr["composite_score"] = fr["company_id"].map(composite_map)

    grp = groups[groups["company_id"] == company_id]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if grp.empty:
        return _standalone_chart(ticker, company_id, fr, composite_map, out_dir, year)

    group_name = grp.iloc[0]["peer_group_name"]
    group_ids = set(groups[groups["peer_group_name"] == group_name]["company_id"])
    peers = fr[fr["company_id"].isin(group_ids)].copy()

    labels = [m[3] for m in METRICS]
    comp_vals = []
    peer_avgs = []
    for name, col, invert, _ in METRICS:
        if col not in peers.columns:
            comp_vals.append(0.0)
            peer_avgs.append(0.0)
            continue
        ranks = _rank_within(peers[col], invert)
        cv = ranks.get(company_id)
        cv = 0.0 if cv is None or pd.isna(cv) else float(cv)
        valid = ranks[ranks.notna()]
        pv = float(valid.mean()) if not valid.empty else 0.0
        comp_vals.append(cv)
        peer_avgs.append(pv)

    for i in range(len(comp_vals)):
        if pd.isna(comp_vals[i]):
            comp_vals[i] = 0.0
        if pd.isna(peer_avgs[i]):
            peer_avgs[i] = 0.0

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += [angles[0]]
    cv = comp_vals + [comp_vals[0]]
    pv = peer_avgs + [peer_avgs[0]]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    ax.fill(angles, cv, alpha=0.25, color="#1f77b4")
    ax.plot(angles, cv, "o-", linewidth=2, color="#1f77b4", label=f"{ticker}")
    ax.plot(angles, pv, "o--", linewidth=1.5, color="gray", label=f"{group_name} avg")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="gray")
    plt.title(
        f"{ticker} - {year} vs {group_name} average",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )
    plt.legend(loc="lower right", bbox_to_anchor=(1.15, -0.05))

    out = out_dir / f"{ticker}_{year}_radar.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def _standalone_chart(ticker, company_id, fr, composite_map, out_dir, year) -> str:
    comp_score = composite_map.get(company_id)
    avg = np.nanmean([v for v in composite_map.values() if pd.notna(v)])

    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [ticker, "Nifty 100 Avg"]
    vals = [comp_score if pd.notna(comp_score) else 0, avg if pd.notna(avg) else 0]
    bars = ax.bar(labels, vals, color=["#1f77b4", "gray"])
    ax.set_ylabel("Composite Quality Score")
    ax.set_title(
        f"{ticker} - Composite Score vs Nifty 100 Average ({year})",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_ylim(0, 100)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.1f}", ha="center")
    plt.tight_layout()

    out = out_dir / f"{ticker}_{year}_radar.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def generate_all(db_path="db/nifty100.db", output_dir="reports/radar_charts/") -> list:
    year, fr, _, _ = _load_latest(db_path)
    generated = []
    for cid in fr["company_id"].unique():
        try:
            generated.append(generate_radar(int(cid), year, db_path, output_dir))
        except Exception:
            continue
    print(f"[Radar] Generated {len(generated)} charts")
    return generated


if __name__ == "__main__":
    generate_all()
