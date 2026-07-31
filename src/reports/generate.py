import logging
import os
import sqlite3
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

import numpy as np

logger = logging.getLogger("reports.generator")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "db", "nifty100.db")
RADAR_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "radar_charts")
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

PAGE_W, PAGE_H = 8.27, 11.69

DARK_BLUE = "#1a3a5c"
WHITE = "#ffffff"
BORDER_COLOR = "#cccccc"
TEXT_DARK = "#1a1a1a"
ACCENT_ORANGE = "#e67e22"
ACCENT_GREEN = "#27ae60"
ACCENT_RED = "#c0392b"
TABLE_HEADER_BG = "#2c3e50"
TABLE_HEADER_FG = "#ffffff"
STRIPE_EVEN = "#f9f9f9"
STRIPE_ODD = "#ffffff"

RATIO_PCT_METRICS = {
    "net_profit_margin", "operating_profit_margin", "gross_profit_margin",
    "roe", "roce", "roa", "roic",
    "dividend_yield", "fcf_yield",
}


def _format_value(val, metric_name=None):
    if val is None:
        return "-"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return str(val)
    if metric_name and metric_name in RATIO_PCT_METRICS:
        return f"{v:,.1f}%"
    if abs(v) >= 1e7:
        return f"{v/1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v/1e5:,.2f} L"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if v == int(v):
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def _fmt_cr(val):
    if val is None:
        return "-"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return str(val)
    if abs(v) >= 1e7:
        return f"{v/1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v/1e5:,.2f} L"
    return f"{v:,.0f}"


def _fmt_pct(val):
    if val is None:
        return "-"
    try:
        return f"{float(val):,.1f}%"
    except (ValueError, TypeError):
        return str(val)


def _safe_float(val):
    if val is None:
        return np.nan
    try:
        return float(val)
    except (ValueError, TypeError):
        return np.nan


def _row_get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        pass
    if hasattr(row, "get"):
        return row.get(key, default)
    return default


def _get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _draw_header(fig, ax, ticker, company_name, sector_name, year=None):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.fill_between([0, 1], 0.92, 1, facecolor=DARK_BLUE, zorder=1)

    rect_header = plt.Rectangle((0, 0.88), 1, 0.12, fill=True,
                                facecolor=DARK_BLUE, edgecolor=None, zorder=1,
                                transform=ax.transAxes)
    ax.add_patch(rect_header)

    ax.text(0.04, 0.93, str(ticker), transform=ax.transAxes,
            fontsize=22, fontweight="bold", color=WHITE, va="center")

    ax.text(0.04, 0.895, f"{company_name}  |  {sector_name or '-'}",
            transform=ax.transAxes, fontsize=10, color="#bdc3c7", va="center")

    if year:
        ax.text(0.96, 0.93, f"FY{year}", transform=ax.transAxes,
                fontsize=16, fontweight="bold", color=WHITE, va="center", ha="right")

    ax.text(0.96, 0.895, "Tearsheet",
            transform=ax.transAxes, fontsize=9, color="#bdc3c7", va="center", ha="right")

    line = plt.Line2D([0, 1], [0.88, 0.88], transform=ax.transAxes,
                      color=ACCENT_ORANGE, linewidth=2, zorder=2)
    ax.add_line(line)


def _draw_footer(fig, ax, page_info=None):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    line = plt.Line2D([0.04, 0.96], [0.15, 0.15], transform=ax.transAxes,
                      color=BORDER_COLOR, linewidth=0.5)
    ax.add_line(line)

    ax.text(0.04, 0.08, f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}",
            transform=ax.transAxes, fontsize=7, color="#999999", va="center")
    ax.text(0.96, 0.08, "Nifty100 Analytics",
            transform=ax.transAxes, fontsize=7, color="#999999", va="center", ha="right")

    if page_info:
        ax.text(0.5, 0.08, page_info, transform=ax.transAxes,
                fontsize=7, color="#999999", va="center", ha="center")


def _draw_table(ax, headers, data, col_widths=None, title=None, y_start=0.95,
                header_color=TABLE_HEADER_BG, header_fg=TABLE_HEADER_FG,
                fontsize=7, header_fontsize=7, title_fontsize=10,
                row_colors=None, col_formatters=None, cell_fontsize=6.5):
    n_rows = len(data)
    n_cols = len(headers)

    if n_rows == 0:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.text(0.5, 0.5, "No data available", transform=ax.transAxes,
                fontsize=10, ha="center", va="center", color="#999999")
        return

    ax.set_xlim(0, 1)
    ax.set_ylim(0, n_rows + 2)
    ax.axis("off")

    if title:
        ax.text(0.04, y_start + 0.3, title, fontsize=title_fontsize,
                fontweight="bold", color=DARK_BLUE, va="bottom")

    if col_widths is None:
        col_widths = [1.0 / n_cols] * n_cols

    total_width = sum(col_widths)
    col_widths_norm = [w / total_width * 0.92 for w in col_widths]
    x_offset = 0.04

    for j, (header, w) in enumerate(zip(headers, col_widths_norm)):
        x_pos = x_offset + sum(col_widths_norm[:j])
        rect = plt.Rectangle((x_pos, n_rows + 0.65), w, 0.26,
                             facecolor=header_color, edgecolor=header_color,
                             transform=ax.transData, clip_on=False)
        ax.add_patch(rect)
        ax.text(x_pos + w / 2, n_rows + 0.78, header,
                fontsize=header_fontsize, fontweight="bold", color=header_fg,
                ha="center", va="center")

    for i, row in enumerate(data):
        y = n_rows - i - 0.5
        bg = STRIPE_EVEN if i % 2 == 0 else STRIPE_ODD
        rect = plt.Rectangle((x_offset, y - 0.25), sum(col_widths_norm), 0.5,
                             facecolor=bg, edgecolor="#e0e0e0", linewidth=0.3,
                             transform=ax.transData, clip_on=False)
        ax.add_patch(rect)

        for j, (cell_val, w) in enumerate(zip(row, col_widths_norm)):
            x_pos = x_offset + sum(col_widths_norm[:j])
            formatted = cell_val
            if col_formatters and j < len(col_formatters) and col_formatters[j]:
                formatted = col_formatters[j](cell_val)

            ax.text(x_pos + w / 2, y, str(formatted),
                    fontsize=cell_fontsize, color=TEXT_DARK,
                    ha="center", va="center")

    ax.set_ylim(-1, n_rows + 1.5)

    return y_start - (n_rows + 0.5) * (0.55 / 3) - 0.1


def _draw_cagr_table(ax, cagr_data, y_start=0.95):
    headers = ["Metric", "3Y CAGR", "5Y CAGR", "10Y CAGR"]
    rows = []
    for metric_label, values in cagr_data.items():
        row_vals = [metric_label]
        for window in ["3y", "5y", "10y"]:
            info = values.get(window, {})
            val = info.get("value")
            flag = info.get("flag")
            if val is not None:
                row_vals.append(f"{val:,.1f}%")
            elif flag:
                row_vals.append(flag)
            else:
                row_vals.append("-")
        rows.append(row_vals)

    _draw_table(ax, headers, rows,
                col_widths=[0.25, 0.25, 0.25, 0.25],
                title="Revenue & PAT Growth (CAGR)", y_start=y_start,
                fontsize=8, cell_fontsize=7)


def _fetch_company(conn, company_id):
    return conn.execute(
        "SELECT * FROM companies WHERE company_id = ?", [company_id]
    ).fetchone()


def _fetch_financial_summary(conn, company_id, limit=5):
    rows = conn.execute(
        """SELECT year, sales, net_profit, eps, operating_profit, operating_profit_margin
           FROM profitandloss
           WHERE company_id = ?
           ORDER BY year DESC
           LIMIT ?""", [company_id, limit]
    ).fetchall()
    return rows[::-1]


def _fetch_key_ratios(conn, company_id, year):
    return conn.execute(
        """SELECT roe, roce, roa, debt_to_equity, interest_coverage,
                  pe_ratio, pb_ratio, fcf_yield, dividend_yield,
                  net_profit_margin, operating_profit_margin
           FROM financial_ratios
           WHERE company_id = ? AND year = ?
           ORDER BY year DESC LIMIT 1""", [company_id, year]
    ).fetchone()


def _fetch_cash_flow(conn, company_id, limit=3):
    rows = conn.execute(
        """SELECT cf.year, cf.operating_activities AS cfo,
                  cf.capex, cf.fcf,
                  COALESCE(fr.allocation_pattern, '-') AS allocation_pattern
           FROM cashflow cf
           LEFT JOIN financial_ratios fr
             ON cf.company_id = fr.company_id AND cf.year = fr.year
           WHERE cf.company_id = ?
           ORDER BY cf.year DESC
           LIMIT ?""", [company_id, limit]
    ).fetchall()
    return rows[::-1]


def _fetch_peer_percentiles(conn, company_id, year):
    return conn.execute(
        """SELECT metric_name, percentile_rank, peer_group
           FROM peer_percentiles
           WHERE company_id = ? AND year = ?
           ORDER BY metric_name""", [company_id, year]
    ).fetchall()


def _fetch_cagr_data(conn, company_id):
    rows = conn.execute(
        """SELECT metric_name, metric_value, description
           FROM analysis
           WHERE company_id = ? AND analysis_type = 'CAGR'
           ORDER BY metric_name""", [company_id]
    ).fetchall()

    cagr_data = {}
    for row in rows:
        mn = row["metric_name"]
        parts = mn.replace("cagr_", "", 1).rsplit("_", 1)
        if len(parts) >= 2:
            metric = "_".join(parts[:-1])
            window = parts[-1]
        else:
            metric = mn
            window = "unknown"

        if metric not in cagr_data:
            cagr_data[metric] = {}
        cagr_data[metric][window] = {
            "value": row["metric_value"],
            "flag": row["description"],
        }
    return cagr_data


def _fetch_latest_year(conn):
    row = conn.execute("SELECT MAX(year) as max_year FROM financial_ratios").fetchone()
    return row["max_year"] if row else None


def _fetch_pros_cons(conn, company_id):
    return conn.execute(
        "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
        [company_id],
    ).fetchone()


def _generate_cagr_fallback(conn, company_id, latest_year):
    cagr_data = {}

    for metric, col in [("revenue", "total_revenue"), ("pat", "net_profit")]:
        years_data = conn.execute(
            f"SELECT year, {col} FROM profitandloss WHERE company_id = ? AND {col} IS NOT NULL ORDER BY year ASC",
            [company_id],
        ).fetchall()

        if len(years_data) < 2:
            continue

        years = [r["year"] for r in years_data]
        values = [r[col] for r in years_data]

        cagr_data[metric] = {}
        for window_name, window_size in [("3y", 3), ("5y", 5), ("10y", 10)]:
            if len(years) < window_size + 1:
                cagr_data[metric][window_name] = {"value": None, "flag": "INSUFFICIENT_DATA"}
                continue

            start_val = values[-(window_size + 1)]
            end_val = values[-1]
            actual_years = years[-1] - years[-(window_size + 1)]
            if actual_years <= 0:
                actual_years = window_size

            if start_val is None or end_val is None or abs(start_val) < 1e-12:
                cagr_data[metric][window_name] = {"value": None, "flag": "ZERO_BASE"}
                continue

            if start_val > 0 and end_val > 0:
                cagr_val = ((end_val / start_val) ** (1.0 / actual_years) - 1) * 100
                cagr_data[metric][window_name] = {"value": round(cagr_val, 2), "flag": "NORMAL"}
            elif start_val > 0 and end_val < 0:
                cagr_data[metric][window_name] = {"value": None, "flag": "DECLINE_TO_LOSS"}
            elif start_val < 0 and end_val > 0:
                cagr_data[metric][window_name] = {"value": None, "flag": "TURNAROUND"}
            elif start_val < 0 and end_val < 0:
                cagr_val = ((abs(end_val) / abs(start_val)) ** (1.0 / actual_years) - 1) * 100
                cagr_data[metric][window_name] = {"value": round(cagr_val, 2), "flag": "BOTH_NEGATIVE"}

    return cagr_data


def generate_tearsheet(company_id, year=None, output_dir=None,
                       db_path=DB_PATH, radar_dir=RADAR_DIR):
    conn = _get_conn(db_path)
    try:
        company = _fetch_company(conn, company_id)
        if not company:
            logger.warning(f"Company {company_id} not found, skipping tearsheet")
            return None

        ticker = company["ticker"]
        company_name = company["company_name"]
        sector_name = _row_get(company, "sector_name") or "Unknown"

        if year is None:
            year = _fetch_latest_year(conn)
        if year is None:
            year = 2024

        if output_dir is None:
            output_dir = os.path.join(PROJECT_ROOT, "reports", "tearsheets")
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f"{ticker}_tearsheet.pdf")

        fin_rows = _fetch_financial_summary(conn, company_id, limit=5)
        ratios = _fetch_key_ratios(conn, company_id, year)
        cf_rows = _fetch_cash_flow(conn, company_id, limit=3)
        peer_rows = _fetch_peer_percentiles(conn, company_id, year)
        cagr_data = _fetch_cagr_data(conn, company_id)
        if not cagr_data:
            cagr_data = _generate_cagr_fallback(conn, company_id, year)
        pros_cons_row = _fetch_pros_cons(conn, company_id)

        radar_path = os.path.join(radar_dir, f"{ticker}_{year}_radar.png")
        has_radar = os.path.isfile(radar_path)

        with PdfPages(output_path) as pdf:

            # ── Page 1: Header + Financial Summary + Key Ratios ──────
            fig1, (ax_header, ax_fin, ax_ratios) = plt.subplots(
                3, 1, figsize=(PAGE_W, PAGE_H),
                gridspec_kw={"height_ratios": [0.8, 4.0, 6.0]}
            )
            _draw_header(fig1, ax_header, ticker, company_name, sector_name, year=year)

            fin_headers = ["Year", "Sales", "Net Profit", "EPS", "OPM %", "NPM %"]
            fin_data = []
            for r in fin_rows:
                sales = r["sales"]
                net_profit = r["net_profit"]
                opm = r["operating_profit_margin"]
                if opm is None and sales and sales != 0 and r["operating_profit"] is not None:
                    opm = (r["operating_profit"] / sales) * 100
                if sales and sales != 0 and net_profit is not None:
                    npm = (net_profit / sales) * 100
                else:
                    npm = None
                fin_data.append([
                    str(r["year"]),
                    _fmt_cr(r["sales"]),
                    _fmt_cr(r["net_profit"]),
                    f"{r['eps']:,.2f}" if r["eps"] is not None else "-",
                    _fmt_pct(opm),
                    _fmt_pct(npm),
                ])

            _draw_table(ax_fin, fin_headers, fin_data,
                        col_widths=[0.10, 0.22, 0.22, 0.14, 0.16, 0.16],
                        title="Financial Summary (5-Year)",
                        y_start=0.98, fontsize=8, cell_fontsize=7)

            ratio_data = [
                {
                    "label": "Return on Equity (ROE)",
                    "value": ratios["roe"] if ratios else None,
                    "interpretation": ">15% Strong · 8-15% Average · <8% Weak",
                },
                {
                    "label": "Return on Capital (ROCE)",
                    "value": ratios["roce"] if ratios else None,
                    "interpretation": ">15% Strong · 8-15% Average · <8% Weak",
                },
                {
                    "label": "Return on Assets (ROA)",
                    "value": ratios["roa"] if ratios else None,
                    "interpretation": ">10% Strong · 5-10% Average · <5% Weak",
                },
                {
                    "label": "Net Profit Margin",
                    "value": ratios["net_profit_margin"] if ratios else None,
                    "interpretation": ">20% Strong · 10-20% Average · <10% Low",
                },
                {
                    "label": "Debt / Equity",
                    "value": ratios["debt_to_equity"] if ratios else None,
                    "interpretation": "<1 Conservative · 1-2 Moderate · >2 High Leverage",
                },
                {
                    "label": "Interest Coverage",
                    "value": ratios["interest_coverage"] if ratios else None,
                    "interpretation": ">3 Comfortable · 2-3 Moderate · <2 Stressed",
                },
                {
                    "label": "P/E Ratio",
                    "value": ratios["pe_ratio"] if ratios else None,
                    "interpretation": "",
                },
                {
                    "label": "P/B Ratio",
                    "value": ratios["pb_ratio"] if ratios else None,
                    "interpretation": "",
                },
                {
                    "label": "FCF Yield",
                    "value": ratios["fcf_yield"] if ratios else None,
                    "interpretation": ">5% Attractive · 2-5% Fair · <2% Expensive",
                },
                {
                    "label": "Dividend Yield",
                    "value": ratios["dividend_yield"] if ratios else None,
                    "interpretation": ">3% High Yield · 1-3% Moderate · <1% Low",
                },
            ]

            ax_ratios.set_xlim(0, 1)
            ax_ratios.set_ylim(0, len(ratio_data) + 1.5)
            ax_ratios.axis("off")
            ax_ratios.text(0.04, len(ratio_data) + 0.5, "Key Financial Ratios",
                           fontsize=10, fontweight="bold", color=DARK_BLUE, va="bottom")

            for i, rd in enumerate(ratio_data):
                y = len(ratio_data) - i - 0.5
                bg = STRIPE_EVEN if i % 2 == 0 else STRIPE_ODD
                rect = plt.Rectangle((0.03, y - 0.35), 0.94, 0.7,
                                     facecolor=bg, edgecolor="#e0e0e0", linewidth=0.3,
                                     transform=ax_ratios.transData, clip_on=False)
                ax_ratios.add_patch(rect)

                ax_ratios.text(0.06, y, rd["label"], fontsize=7,
                               fontweight="bold", color=DARK_BLUE, va="center")

                if rd["value"] is not None:
                    try:
                        v = float(rd["value"])
                        if rd["label"] in ("Debt / Equity", "P/E Ratio", "P/B Ratio",
                                           "Interest Coverage"):
                            val_str = f"{v:,.2f}"
                        else:
                            val_str = f"{v:,.1f}%"
                    except (ValueError, TypeError):
                        val_str = "-"
                else:
                    val_str = "-"
                ax_ratios.text(0.52, y, val_str, fontsize=7,
                               fontweight="bold", color=TEXT_DARK, va="center",
                               ha="center")

                ax_ratios.text(0.62, y, rd["interpretation"], fontsize=5.5,
                               color="#7f8c8d", va="center")

            _draw_footer(fig1, ax_ratios, page_info="Page 1/3")
            fig1.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                 hspace=0.15)
            pdf.savefig(fig1, dpi=150)
            plt.close(fig1)

            # ── Page 2: Cash Flow + Peer Percentiles + CAGR ──────────
            fig2, (ax_cf, ax_peer, ax_cagr) = plt.subplots(
                3, 1, figsize=(PAGE_W, PAGE_H),
                gridspec_kw={"height_ratios": [3.5, 5.5, 5.5]}
            )

            cf_headers = ["Year", "CFO", "CAPEX", "FCF", "Allocation"]
            cf_data = []
            for r in cf_rows:
                cf_data.append([
                    str(r["year"]),
                    _fmt_cr(r["cfo"]),
                    _fmt_cr(r["capex"]),
                    _fmt_cr(r["fcf"]),
                    str(r["allocation_pattern"]) if r["allocation_pattern"] else "-",
                ])
            _draw_table(ax_cf, cf_headers, cf_data,
                        col_widths=[0.12, 0.22, 0.22, 0.22, 0.22],
                        title="Cash Flow Trends (3-Year)", y_start=1.05,
                        fontsize=8, cell_fontsize=7)

            if peer_rows:
                metric_display = {
                    "net_profit_margin": "Net Profit Margin",
                    "operating_profit_margin": "Operating Margin",
                    "roe": "ROE",
                    "roce": "ROCE",
                    "roa": "ROA",
                    "debt_to_equity": "Debt/Equity",
                    "interest_coverage": "Int. Coverage",
                    "asset_turnover": "Asset Turnover",
                    "pe_ratio": "P/E Ratio",
                    "fcf_yield": "FCF Yield",
                }
                peer_headers = ["Metric", "Percentile", "Peer Group"]
                peer_data = []
                for r in peer_rows:
                    mn = r["metric_name"]
                    pr_val = r["percentile_rank"]
                    pg = r["peer_group"] or "-"
                    display_name = metric_display.get(mn, mn)
                    pct_str = f"{pr_val:,.0f}%" if pr_val is not None else "-"
                    peer_data.append([display_name, pct_str, pg])

                _draw_table(ax_peer, peer_headers, peer_data,
                            col_widths=[0.35, 0.25, 0.40],
                            title="Peer Percentile Ranks",
                            y_start=1.05, fontsize=8, cell_fontsize=7)
            else:
                ax_peer.axis("off")
                ax_peer.text(0.5, 0.5, "Peer percentile data not available",
                             transform=ax_peer.transAxes, fontsize=9,
                             ha="center", va="center", color="#999999")

            if cagr_data:
                _draw_cagr_table(ax_cagr, cagr_data, y_start=1.05)
            else:
                ax_cagr.axis("off")
                ax_cagr.text(0.5, 0.5, "CAGR data not available",
                             transform=ax_cagr.transAxes, fontsize=9,
                             ha="center", va="center", color="#999999")

            for ax in [ax_cf, ax_peer, ax_cagr]:
                _draw_footer(fig2, ax, page_info="Page 2/3")

            fig2.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                 hspace=0.25)
            pdf.savefig(fig2, dpi=150)
            plt.close(fig2)

            # ── Page 3: Radar Chart + Pros/Cons ───────────────────────
            page3_has_content = has_radar or pros_cons_row

            if page3_has_content:
                fig3, (ax_radar, ax_proscons) = plt.subplots(
                    2, 1, figsize=(PAGE_W, PAGE_H),
                    gridspec_kw={"height_ratios": [6.5, 5.5]}
                )

                if has_radar:
                    try:
                        img = plt.imread(radar_path)
                        ax_radar.imshow(img)
                        ax_radar.axis("off")
                        ax_radar.set_title("Performance Radar vs Sector Average",
                                           fontsize=11, fontweight="bold",
                                           color=DARK_BLUE, pad=5)
                    except Exception as e:
                        logger.warning(f"Failed to load radar image for {ticker}: {e}")
                        ax_radar.axis("off")
                        ax_radar.text(0.5, 0.5, "Radar chart unavailable",
                                      transform=ax_radar.transAxes, fontsize=10,
                                      ha="center", va="center", color="#999999")
                else:
                    ax_radar.axis("off")
                    ax_radar.text(0.5, 0.5, "Radar chart not available",
                                  transform=ax_radar.transAxes, fontsize=10,
                                  ha="center", va="center", color="#999999")

                ax_proscons.axis("off")
                ax_proscons.set_xlim(0, 1)
                ax_proscons.set_ylim(0, 1)

                if pros_cons_row:
                    pros_text = pros_cons_row["pros"] or "N/A"
                    cons_text = pros_cons_row["cons"] or "N/A"

                    box_left = 0.03
                    box_width = 0.44
                    box_height = 0.5

                    ax_proscons.text(box_left + box_width / 2, 0.92,
                                     "Strengths", fontsize=11,
                                     fontweight="bold", color=ACCENT_GREEN,
                                     ha="center", va="top")

                    rect_pros = plt.Rectangle(
                        (box_left, 0.38), box_width, box_height,
                        facecolor="#eafaf1", edgecolor=ACCENT_GREEN, linewidth=1,
                        transform=ax_proscons.transAxes, clip_on=False
                    )
                    ax_proscons.add_patch(rect_pros)
                    ax_proscons.text(box_left + 0.02, 0.86, pros_text[:600],
                                     fontsize=6.5, color=TEXT_DARK,
                                     va="top", ha="left",
                                     transform=ax_proscons.transAxes,
                                     wrap=True)

                    ax_proscons.text(0.56 + box_width / 2, 0.92,
                                     "Risks / Concerns", fontsize=11,
                                     fontweight="bold", color=ACCENT_RED,
                                     ha="center", va="top")

                    rect_cons = plt.Rectangle(
                        (0.56, 0.38), box_width, box_height,
                        facecolor="#fdedec", edgecolor=ACCENT_RED, linewidth=1,
                        transform=ax_proscons.transAxes, clip_on=False
                    )
                    ax_proscons.add_patch(rect_cons)
                    ax_proscons.text(0.58, 0.86, cons_text[:600],
                                     fontsize=6.5, color=TEXT_DARK,
                                     va="top", ha="left",
                                     transform=ax_proscons.transAxes,
                                     wrap=True)
                else:
                    ax_proscons.text(0.5, 0.7, "Pros & Cons data not available",
                                     transform=ax_proscons.transAxes, fontsize=9,
                                     ha="center", va="center", color="#999999")

                _draw_footer(fig3, ax_proscons, page_info="Page 3/3")
                fig3.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                     hspace=0.15)
                pdf.savefig(fig3, dpi=150)
                plt.close(fig3)

        logger.info(f"Generated tearsheet: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to generate tearsheet for company {company_id}: {e}",
                     exc_info=True)
        return None
    finally:
        conn.close()


def generate_sector_report(sector_name, output_dir=None, db_path=DB_PATH):
    conn = _get_conn(db_path)
    try:
        if output_dir is None:
            output_dir = os.path.join(PROJECT_ROOT, "reports", "sector_pdfs")
        os.makedirs(output_dir, exist_ok=True)

        safe_name = sector_name.replace(" ", "_").replace("/", "_")
        output_path = os.path.join(output_dir, f"{safe_name}_sector_report.pdf")

        latest_year = _fetch_latest_year(conn)

        companies_rows = conn.execute(
            """SELECT company_id, ticker, company_name, market_cap
               FROM companies
               WHERE sector_name = ?
               ORDER BY market_cap DESC""", [sector_name]
        ).fetchall()

        if not companies_rows:
            logger.warning(f"No companies found in sector: {sector_name}")
            return None

        company_ids = [r["company_id"] for r in conn.execute(
            "SELECT company_id FROM companies WHERE sector_name = ?", [sector_name]
        ).fetchall()]

        placeholders = ",".join("?" for _ in company_ids)
        ratios_rows = conn.execute(
            f"""SELECT roe, roce, net_profit_margin, debt_to_equity, company_id
                FROM financial_ratios
                WHERE company_id IN ({placeholders}) AND year = ?""",
            company_ids + [latest_year],
        ).fetchall() if company_ids else []

        with PdfPages(output_path) as pdf:

            # ── Page 1: Title page ────────────────────────────────────
            fig1, ax1 = plt.subplots(figsize=(PAGE_W, PAGE_H))
            ax1.set_xlim(0, 1)
            ax1.set_ylim(0, 1)
            ax1.axis("off")

            rect_bg = plt.Rectangle((0, 0), 1, 1, facecolor=DARK_BLUE,
                                    transform=ax1.transAxes)
            ax1.add_patch(rect_bg)

            ax1.text(0.5, 0.65, sector_name, transform=ax1.transAxes,
                     fontsize=32, fontweight="bold", color=WHITE, ha="center", va="center")

            ax1.text(0.5, 0.55, "Sector Analysis Report",
                     transform=ax1.transAxes,
                     fontsize=16, color="#bdc3c7", ha="center", va="center")

            line = plt.Line2D([0.3, 0.7], [0.50, 0.50], transform=ax1.transAxes,
                              color=ACCENT_ORANGE, linewidth=2)
            ax1.add_line(line)

            ax1.text(0.5, 0.40, f"Companies: {len(companies_rows)}",
                     transform=ax1.transAxes,
                     fontsize=12, color=WHITE, ha="center", va="center")
            ax1.text(0.5, 0.35, f"Data as of FY{latest_year}",
                     transform=ax1.transAxes,
                     fontsize=12, color=WHITE, ha="center", va="center")
            ax1.text(0.5, 0.25, f"Generated: {datetime.now().strftime('%d-%b-%Y')}",
                     transform=ax1.transAxes,
                     fontsize=10, color="#bdc3c7", ha="center", va="center")

            ax1.text(0.5, 0.08, "Nifty100 Analytics", transform=ax1.transAxes,
                     fontsize=8, color="#7f8c8d", ha="center", va="center")

            pdf.savefig(fig1, dpi=150)
            plt.close(fig1)

            # ── Page 2: Companies Table + Aggregate Metrics ───────────
            fig2, (ax_companies, ax_agg) = plt.subplots(
                2, 1, figsize=(PAGE_W, PAGE_H),
                gridspec_kw={"height_ratios": [6.5, 4.5]}
            )

            comp_headers = ["Ticker", "Company", "Market Cap"]
            comp_data = []
            for r in companies_rows:
                comp_data.append([
                    r["ticker"],
                    r["company_name"],
                    _fmt_cr(r["market_cap"]),
                ])
            _draw_table(ax_companies, comp_headers, comp_data,
                        col_widths=[0.20, 0.45, 0.35],
                        title=f"Companies in {sector_name}",
                        y_start=1.05, fontsize=8, cell_fontsize=6.5)

            metric_names = ["roe", "roce", "net_profit_margin", "debt_to_equity"]
            agg_headers = ["Metric", "Avg", "Median", "Min", "Max"]
            agg_data = []
            for mn in metric_names:
                vals = [_safe_float(r[mn]) for r in ratios_rows if r[mn] is not None]
                if vals:
                    avg_v = np.nanmean(vals)
                    med_v = np.nanmedian(vals)
                    min_v = np.nanmin(vals)
                    max_v = np.nanmax(vals)
                else:
                    avg_v = med_v = min_v = max_v = float("nan")

                display_name = {
                    "roe": "ROE", "roce": "ROCE",
                    "net_profit_margin": "Net Profit Margin",
                    "debt_to_equity": "D/E Ratio",
                }.get(mn, mn)

                agg_data.append([
                    display_name,
                    _fmt_pct(avg_v) if not np.isnan(avg_v) else "-",
                    _fmt_pct(med_v) if not np.isnan(med_v) else "-",
                    _fmt_pct(min_v) if not np.isnan(min_v) else "-",
                    _fmt_pct(max_v) if not np.isnan(max_v) else "-",
                ])

            mcap_vals = [_safe_float(r["market_cap"]) for r in companies_rows
                         if r["market_cap"] is not None]
            if mcap_vals:
                mcap_avg = np.nanmean(mcap_vals)
                mcap_med = np.nanmedian(mcap_vals)
                mcap_min = np.nanmin(mcap_vals)
                mcap_max = np.nanmax(mcap_vals)
                agg_data.append([
                    "Market Cap",
                    _fmt_cr(mcap_avg), _fmt_cr(mcap_med),
                    _fmt_cr(mcap_min), _fmt_cr(mcap_max),
                ])

            _draw_table(ax_agg, agg_headers, agg_data,
                        col_widths=[0.30, 0.20, 0.20, 0.15, 0.15],
                        title="Sector Aggregate Metrics",
                        y_start=1.05, fontsize=8, cell_fontsize=7)

            fig2.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                 hspace=0.25)
            pdf.savefig(fig2, dpi=150)
            plt.close(fig2)

            # ── Page 3: Top/Bottom by ROE + Growth ────────────────────
            fig3, (ax_top, ax_bot) = plt.subplots(
                2, 1, figsize=(PAGE_W, PAGE_H),
                gridspec_kw={"height_ratios": [5.5, 5.5]}
            )

            company_roe = []
            for r in ratios_rows:
                if r["roe"] is not None:
                    company_roe.append((r["company_id"], float(r["roe"])))
            company_roe.sort(key=lambda x: x[1], reverse=True)

            def _draw_ranked_table(ax, title_text, items, limit=3, ascending=False):
                ticker_map = {}
                for cr in companies_rows:
                    ticker_map[cr["company_id"]] = cr

                headers = ["Rank", "Ticker", "Company", "ROE"]
                rows_to_show = items[:limit] if not ascending else items[-limit:][::-1]
                if ascending:
                    rows_to_show = items[-limit:][::-1]

                data = []
                for rank, (cid, roe_val) in enumerate(rows_to_show, 1):
                    comp = ticker_map.get(cid)
                    data.append([
                        str(rank),
                        comp["ticker"] if comp else str(cid),
                        comp["company_name"] if comp else "-",
                        f"{roe_val:,.1f}%",
                    ])

                if not ascending:
                    data = []
                    for rank, (cid, roe_val) in enumerate(items[:limit], 1):
                        comp = ticker_map.get(cid)
                        data.append([
                            str(rank),
                            comp["ticker"] if comp else str(cid),
                            comp["company_name"] if comp else "-",
                            f"{roe_val:,.1f}%",
                        ])

                _draw_table(ax, headers, data,
                            col_widths=[0.10, 0.25, 0.40, 0.25],
                            title=title_text, y_start=1.05,
                            fontsize=8, cell_fontsize=7)

            _draw_ranked_table(ax_top, "Top Performers by ROE", company_roe, limit=3)
            _draw_ranked_table(ax_bot, "Bottom Performers by ROE", company_roe, limit=3,
                               ascending=True)

            fig3.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                 hspace=0.20)
            pdf.savefig(fig3, dpi=150)
            plt.close(fig3)

        logger.info(f"Generated sector report: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to generate sector report for {sector_name}: {e}",
                     exc_info=True)
        return None
    finally:
        conn.close()


def generate_portfolio_summary(output_path=None, db_path=DB_PATH):
    conn = _get_conn(db_path)
    try:
        if output_path is None:
            output_path = os.path.join(PROJECT_ROOT, "reports", "portfolio_summary.pdf")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        latest_year = _fetch_latest_year(conn)

        companies = conn.execute(
            """SELECT c.*, fr.roe, fr.roce, fr.net_profit_margin, fr.debt_to_equity,
                      fr.fcf_yield, fr.pe_ratio, fr.pb_ratio, fr.interest_coverage,
                      fr.operating_profit_margin
               FROM companies c
               LEFT JOIN financial_ratios fr
                 ON c.company_id = fr.company_id AND fr.year = ?""",
            [latest_year],
        ).fetchall()

        sectors = conn.execute(
            "SELECT DISTINCT sector_name FROM companies WHERE sector_name IS NOT NULL ORDER BY sector_name"
        ).fetchall()
        sector_names = [s["sector_name"] for s in sectors]

        with PdfPages(output_path) as pdf:

            # ── Page 1: Title ─────────────────────────────────────────
            fig_title, ax_title = plt.subplots(figsize=(PAGE_W, PAGE_H))
            ax_title.set_xlim(0, 1)
            ax_title.set_ylim(0, 1)
            ax_title.axis("off")

            rect_bg = plt.Rectangle((0, 0), 1, 1, facecolor=DARK_BLUE,
                                    transform=ax_title.transAxes)
            ax_title.add_patch(rect_bg)

            ax_title.text(0.5, 0.65, "Nifty 100 Portfolio", transform=ax_title.transAxes,
                          fontsize=34, fontweight="bold", color=WHITE, ha="center", va="center")

            ax_title.text(0.5, 0.55, "Summary & Analytics Report",
                          transform=ax_title.transAxes,
                          fontsize=18, color="#bdc3c7", ha="center", va="center")

            line = plt.Line2D([0.3, 0.7], [0.50, 0.50], transform=ax_title.transAxes,
                              color=ACCENT_ORANGE, linewidth=2)
            ax_title.add_line(line)

            active_count = len(companies)
            ax_title.text(0.5, 0.40, f"Companies: {active_count}",
                          transform=ax_title.transAxes,
                          fontsize=14, color=WHITE, ha="center", va="center")
            ax_title.text(0.5, 0.34, f"Sectors: {len(sector_names)}",
                          transform=ax_title.transAxes,
                          fontsize=14, color=WHITE, ha="center", va="center")
            ax_title.text(0.5, 0.28, f"Data as of FY{latest_year}",
                          transform=ax_title.transAxes,
                          fontsize=12, color=WHITE, ha="center", va="center")
            ax_title.text(0.5, 0.20, f"Generated: {datetime.now().strftime('%d-%b-%Y')}",
                          transform=ax_title.transAxes,
                          fontsize=10, color="#bdc3c7", ha="center", va="center")

            ax_title.text(0.5, 0.08, "Nifty100 Analytics", transform=ax_title.transAxes,
                          fontsize=8, color="#7f8c8d", ha="center", va="center")

            pdf.savefig(fig_title, dpi=150)
            plt.close(fig_title)

            # ── Page 2: Market Cap Pie + Sector Table ─────────────────
            fig2, (ax_pie, ax_sector_tbl) = plt.subplots(
                1, 2, figsize=(PAGE_W, PAGE_H * 0.6),
                gridspec_kw={"width_ratios": [1.2, 1.0]}
            )

            sector_mcap = {}
            for c in companies:
                sn = _row_get(c, "sector_name") or "Other"
                mc = _safe_float(c["market_cap"] if "market_cap" in c.keys() else None)
                if not np.isnan(mc) and mc > 0:
                    sector_mcap[sn] = sector_mcap.get(sn, 0) + mc

            if sector_mcap:
                sorted_sectors = sorted(sector_mcap.items(), key=lambda x: x[1], reverse=True)
                labels = [s[0] for s in sorted_sectors]
                sizes = [s[1] for s in sorted_sectors]
                total_mcap = sum(sizes)
                label_with_pct = [
                    f"{lbl}\n({sz/total_mcap*100:.1f}%)"
                    for lbl, sz in zip(labels, sizes)
                ]
                colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))

                wedges, texts = ax_pie.pie(
                    sizes, labels=None, colors=colors, startangle=90,
                    pctdistance=0.85, wedgeprops={"edgecolor": "white", "linewidth": 0.5}
                )
                ax_pie.set_title("Market Cap Distribution by Sector",
                                 fontsize=10, fontweight="bold", color=DARK_BLUE, pad=12)

                ax_pie.legend(wedges, label_with_pct, title="Sectors",
                              loc="center left", bbox_to_anchor=(1, 0, 0.5, 1),
                              fontsize=6.5, title_fontsize=7)
            else:
                ax_pie.axis("off")
                ax_pie.text(0.5, 0.5, "No market cap data",
                            transform=ax_pie.transAxes, ha="center", fontsize=10)

            sector_agg = {}
            for sn in sector_names:
                group = [c for c in companies if _row_get(c, "sector_name") == sn]
                roes = [_safe_float(_row_get(c, "roe")) for c in group if _row_get(c, "roe") is not None]
                nppms = [_safe_float(_row_get(c, "net_profit_margin")) for c in group if _row_get(c, "net_profit_margin") is not None]
                mcap_vals = [_safe_float(_row_get(c, "market_cap")) for c in group if _row_get(c, "market_cap") is not None]
                des = [_safe_float(_row_get(c, "debt_to_equity")) for c in group if _row_get(c, "debt_to_equity") is not None]
                sector_agg[sn] = {
                    "count": len(group),
                    "avg_roe": np.nanmean(roes) if roes else np.nan,
                    "avg_npm": np.nanmean(nppms) if nppms else np.nan,
                    "avg_de": np.nanmean(des) if des else np.nan,
                    "total_mcap": np.nansum(mcap_vals) if mcap_vals else np.nan,
                }

            sector_headers = ["Sector", "#", "Avg ROE", "Avg NPM", "Avg D/E", "Mcap"]
            sector_rows = []
            for sn, agg in sorted(sector_agg.items(), key=lambda x: x[1]["total_mcap"], reverse=True):
                sector_rows.append([
                    sn,
                    str(agg["count"]),
                    _fmt_pct(agg["avg_roe"]) if not np.isnan(agg["avg_roe"]) else "-",
                    _fmt_pct(agg["avg_npm"]) if not np.isnan(agg["avg_npm"]) else "-",
                    f"{agg['avg_de']:,.2f}" if not np.isnan(agg["avg_de"]) else "-",
                    _fmt_cr(agg["total_mcap"]) if not np.isnan(agg["total_mcap"]) else "-",
                ])

            _draw_table(ax_sector_tbl, sector_headers, sector_rows,
                        col_widths=[0.25, 0.08, 0.15, 0.15, 0.15, 0.22],
                        title="Sector-Wise Aggregate Metrics",
                        y_start=1.05, fontsize=8, cell_fontsize=6.5)

            fig2.subplots_adjust(left=0.04, right=0.96, top=0.95, bottom=0.05,
                                 wspace=0.35)
            pdf.savefig(fig2, dpi=150)
            plt.close(fig2)

            # ── Page 3: Top 10 Tables ─────────────────────────────────
            fig3, (ax_mcap, ax_roe, ax_fcf) = plt.subplots(
                3, 1, figsize=(PAGE_W, PAGE_H),
                gridspec_kw={"height_ratios": [4.0, 4.0, 4.0]}
            )

            def _draw_top_table(ax, all_companies, sort_key, title_text, is_pct=False,
                                limit=10):
                sorted_list = sorted(
                    [c for c in all_companies if _row_get(c, sort_key) is not None],
                    key=lambda x: _safe_float(_row_get(x, sort_key)),
                    reverse=True,
                )[:limit]

                headers = ["Rank", "Ticker", "Company", "Sector",
                           sort_key.replace("_", " ").title()]
                data = []
                for i, c in enumerate(sorted_list, 1):
                    val = _safe_float(_row_get(c, sort_key))
                    data.append([
                        str(i),
                        _row_get(c, "ticker", "-"),
                        _row_get(c, "company_name", "-"),
                        _row_get(c, "sector_name", "-") or "-",
                        _fmt_pct(val) if is_pct else _fmt_cr(val),
                    ])

                _draw_table(ax, headers, data,
                            col_widths=[0.06, 0.16, 0.28, 0.25, 0.25],
                            title=title_text, y_start=1.05,
                            fontsize=8, cell_fontsize=6.5)

            _draw_top_table(ax_mcap, companies, "market_cap",
                            "Top 10 by Market Cap")
            _draw_top_table(ax_roe, companies, "roe",
                            "Top 10 by Return on Equity (ROE)", is_pct=True)
            _draw_top_table(ax_fcf, companies, "fcf_yield",
                            "Top 10 by FCF Yield", is_pct=True)

            fig3.subplots_adjust(left=0.04, right=0.96, top=0.98, bottom=0.03,
                                 hspace=0.25)
            pdf.savefig(fig3, dpi=150)
            plt.close(fig3)

        logger.info(f"Generated portfolio summary: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to generate portfolio summary: {e}", exc_info=True)
        return None
    finally:
        conn.close()


def generate_all(db_path=DB_PATH, radar_dir=RADAR_DIR):
    conn = _get_conn(db_path)
    try:
        companies = conn.execute(
            "SELECT company_id, ticker FROM companies"
        ).fetchall()

        sectors = conn.execute(
            "SELECT DISTINCT sector_name FROM companies WHERE sector_name IS NOT NULL"
        ).fetchall()

    finally:
        conn.close()

    # ── Tearsheets ────────────────────────────────────────────────────
    logger.info(f"Generating tearsheets for {len(companies)} companies...")
    success_tears = 0
    for company in companies:
        cid = company["company_id"]
        ticker = company["ticker"]
        try:
            result = generate_tearsheet(cid, db_path=db_path, radar_dir=radar_dir)
            if result:
                success_tears += 1
        except Exception as e:
            logger.warning(f"Tearsheet failed for {ticker} (id={cid}): {e}")

    logger.info(f"Tearsheets: {success_tears}/{len(companies)} generated successfully")

    # ── Sector Reports ────────────────────────────────────────────────
    logger.info(f"Generating sector reports for {len(sectors)} sectors...")
    success_sectors = 0
    for s in sectors:
        sn = s["sector_name"]
        try:
            result = generate_sector_report(sn, db_path=db_path)
            if result:
                success_sectors += 1
        except Exception as e:
            logger.warning(f"Sector report failed for {sn}: {e}")

    logger.info(f"Sector reports: {success_sectors}/{len(sectors)} generated successfully")

    # ── Portfolio Summary ─────────────────────────────────────────────
    logger.info("Generating portfolio summary...")
    summary_result = generate_portfolio_summary(db_path=db_path)
    if summary_result:
        logger.info("Portfolio summary generated successfully")

    return {
        "tearsheets": success_tears,
        "total_companies": len(companies),
        "sector_reports": success_sectors,
        "total_sectors": len(sectors),
        "portfolio_summary": summary_result is not None,
    }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger.setLevel(logging.INFO)

    logger.info("=" * 50)
    logger.info("Nifty100 Analytics - PDF Report Generator")
    logger.info("=" * 50)

    result = generate_all()

    logger.info("-" * 30)
    logger.info("Generation Summary:")
    logger.info(f"  Tearsheets:    {result['tearsheets']}/{result['total_companies']}")
    logger.info(f"  Sector Reports: {result['sector_reports']}/{result['total_sectors']}")
    logger.info(f"  Portfolio Summary: {'Yes' if result['portfolio_summary'] else 'No'}")
    logger.info("=" * 50)

    return result


if __name__ == "__main__":
    main()
