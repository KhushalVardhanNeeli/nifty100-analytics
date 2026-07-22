import sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path


def _get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _compute_cagr(conn, company_id, period=3, latest_year=None):
    if latest_year is None:
        row = conn.execute("SELECT MAX(year) as max_year FROM profitandloss").fetchone()
        latest_year = row["max_year"]

    start_year = latest_year - period
    rows = conn.execute(
        """SELECT year, sales FROM profitandloss
           WHERE company_id = ? AND year IN (?, ?)
           ORDER BY year""",
        [company_id, start_year, latest_year],
    ).fetchall()

    if len(rows) < 2:
        return np.nan

    sales_start = rows[0]["sales"]
    sales_end = rows[-1]["sales"]

    if sales_start <= 0:
        return np.nan

    cagr = ((sales_end / sales_start) ** (1.0 / period) - 1) * 100
    return cagr


def _get_peer_averages(conn, company_id, sector_name):
    ratios = conn.execute(
        """SELECT fr.* FROM financial_ratios fr
           JOIN companies c ON fr.company_id = c.company_id
           WHERE c.sector_name = ? AND fr.company_id != ?
           AND fr.year = (SELECT MAX(year) FROM financial_ratios)""",
        [sector_name, company_id],
    ).fetchall()

    if not ratios:
        return {}

    metrics = [
        "roe", "roce", "net_profit_margin", "asset_turnover",
        "debt_to_equity", "interest_coverage", "fcf_yield",
    ]

    avg = {}
    for m in metrics:
        vals = [r[m] for r in ratios if r[m] is not None]
        if vals:
            avg[m] = np.mean(vals)
        else:
            avg[m] = np.nan

    pids = [r["company_id"] for r in ratios]
    cagrs = []
    for pid in pids[:20]:
        c = _compute_cagr(conn, pid, period=3)
        if not np.isnan(c):
            cagrs.append(c)
    avg["revenue_growth"] = np.mean(cagrs) if cagrs else np.nan

    return avg


def generate_radar(company_id, year, db_path, output_dir="reports/radar_charts/"):
    conn = _get_conn(db_path)
    try:
        company = conn.execute(
            "SELECT ticker, company_name, sector_name FROM companies WHERE company_id = ?",
            [company_id],
        ).fetchone()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        ticker = company["ticker"]
        sector_name = company["sector_name"]

        ratios = conn.execute(
            "SELECT * FROM financial_ratios WHERE company_id = ? AND year = ?",
            [company_id, year],
        ).fetchone()

        if not ratios:
            raise ValueError(f"No ratios for company {company_id} year {year}")

        revenue_growth = _compute_cagr(conn, company_id, period=3, latest_year=year)

        peer_avg = _get_peer_averages(conn, company_id, sector_name)

        axes_labels = [
            "ROE",
            "ROCE",
            "Net Profit\nMargin",
            "Revenue\nGrowth",
            "Asset\nTurnover",
            "Debt/Equity\n(inv)",
            "Interest\nCoverage",
            "FCF Yield",
        ]

        def safe_val(val):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return np.nan
            return float(val)

        company_values = [
            safe_val(ratios["roe"]),
            safe_val(ratios["roce"]),
            safe_val(ratios["net_profit_margin"]),
            safe_val(revenue_growth),
            safe_val(ratios["asset_turnover"]),
            safe_val(1.0 / ratios["debt_to_equity"]) if safe_val(ratios["debt_to_equity"]) and safe_val(ratios["debt_to_equity"]) > 0 else np.nan,
            safe_val(ratios["interest_coverage"]),
            safe_val(ratios["fcf_yield"]),
        ]

        peer_values = [
            safe_val(peer_avg.get("roe", np.nan)),
            safe_val(peer_avg.get("roce", np.nan)),
            safe_val(peer_avg.get("net_profit_margin", np.nan)),
            safe_val(peer_avg.get("revenue_growth", np.nan)),
            safe_val(peer_avg.get("asset_turnover", np.nan)),
            safe_val(1.0 / peer_avg.get("debt_to_equity", np.nan)) if safe_val(peer_avg.get("debt_to_equity", np.nan)) and safe_val(peer_avg.get("debt_to_equity", np.nan)) > 0 else np.nan,
            safe_val(peer_avg.get("interest_coverage", np.nan)),
            safe_val(peer_avg.get("fcf_yield", np.nan)),
        ]

        valid_axes = [
            i for i, (cv, pv) in enumerate(zip(company_values, peer_values))
            if not (np.isnan(cv) and np.isnan(pv))
        ]

        if len(valid_axes) < 3:
            raise ValueError(f"Not enough valid metrics for radar chart (company {ticker})")

        labels = [axes_labels[i] for i in valid_axes]
        comp_vals = [company_values[i] for i in valid_axes]
        peer_vals = [peer_values[i] for i in valid_axes]

        for i in range(len(comp_vals)):
            if np.isnan(comp_vals[i]):
                comp_vals[i] = 0
            if np.isnan(peer_vals[i]):
                peer_vals[i] = 0

        max_vals = [max(abs(comp_vals[i]), abs(peer_vals[i])) for i in range(len(comp_vals))]
        max_vals = [max(v, 0.01) for v in max_vals]

        comp_norm = [comp_vals[i] / max_vals[i] * 100 for i in range(len(comp_vals))]
        peer_norm = [peer_vals[i] / max_vals[i] * 100 for i in range(len(comp_vals))]

        n = len(labels)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += [angles[0]]

        comp_norm += [comp_norm[0]]
        peer_norm += [peer_norm[0]]

        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

        ax.fill(angles, comp_norm, alpha=0.25, color="#1f77b4")
        ax.plot(angles, comp_norm, "o-", linewidth=2, color="#1f77b4", label=f"{ticker}")

        ax.fill(angles, peer_norm, alpha=0.10, color="gray")
        ax.plot(angles, peer_norm, "o--", linewidth=1.5, color="gray", label=f"{sector_name} Avg")

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=10)

        ax.set_rlabel_position(30)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="gray")
        ax.set_ylim(0, 100)

        plt.title(f"{ticker} - {year} vs {sector_name} Average", fontsize=14, fontweight="bold", pad=20)
        plt.legend(loc="lower right", bbox_to_anchor=(0.1, -0.05))

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / f"{ticker}_{year}_radar.png"
        plt.savefig(file_path, dpi=300, bbox_inches="tight")
        plt.close(fig)

        return str(file_path)

    finally:
        conn.close()


def generate_all(db_path, output_dir="reports/radar_charts/"):
    conn = _get_conn(db_path)
    try:
        latest_year = conn.execute(
            "SELECT MAX(year) as max_year FROM financial_ratios"
        ).fetchone()["max_year"]

        companies = conn.execute("SELECT company_id FROM companies").fetchall()

        generated = []
        for company in companies:
            company_id = company["company_id"]
            try:
                path = generate_radar(company_id, latest_year, db_path, output_dir)
                generated.append(path)
            except Exception:
                pass

        return generated

    finally:
        conn.close()
