"""Company tearsheet PDF generator — Sprint 5 (Day 33).

Two-page ReportLab tearsheet per company:
  Page 1: navy header, 6 KPI tiles, 10-year revenue/profit bars, ROE/ROCE lines
  Page 2: balance-sheet composition, cash-flow waterfall, pros & cons, capital badge
"""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import create_engine, text

NAVY = colors.HexColor("#1F3864")
GREEN = colors.HexColor("#2E7D32")
RED = colors.HexColor("#C62828")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
REPORTS_DIR = "reports/tearsheets"


def _load_company(engine, cid):
    comp = pd.read_sql(
        text("SELECT * FROM companies WHERE company_id = :c"), engine, params={"c": cid}
    )
    if comp.empty:
        return None
    comp = comp.iloc[0]
    fr = pd.read_sql(
        text("SELECT * FROM financial_ratios WHERE company_id = :c ORDER BY year"),
        engine,
        params={"c": cid},
    )
    pl = pd.read_sql(
        text("SELECT * FROM profitandloss WHERE company_id = :c ORDER BY year"),
        engine,
        params={"c": cid},
    )
    bs = pd.read_sql(
        text("SELECT * FROM balancesheet WHERE company_id = :c ORDER BY year"),
        engine,
        params={"c": cid},
    )
    cf = pd.read_sql(
        text("SELECT * FROM cashflow WHERE company_id = :c ORDER BY year"),
        engine,
        params={"c": cid},
    )
    return comp, fr, pl, bs, cf


def _chart_png(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def revenue_profit_chart(pl, path):
    d = pl.tail(10)[["year", "sales", "net_profit"]]
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    x = range(len(d))
    ax.bar([i - 0.2 for i in x], d["sales"], width=0.4, label="Sales", color="#4472C4")
    ax.bar(
        [i + 0.2 for i in x],
        d["net_profit"],
        width=0.4,
        label="Net Profit",
        color="#70AD47",
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(d["year"], rotation=45, fontsize=7)
    ax.legend(fontsize=7)
    ax.set_title("Revenue and Net Profit", fontsize=10)
    fig.tight_layout()
    return _chart_png(fig, path)


def roe_roce_chart(fr, path):
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    ax.plot(fr["year"], fr["return_on_equity_pct"], "o-", label="ROE %", color="#1F3864")
    ax2 = ax.twinx()
    ax2.plot(
        fr["year"],
        fr["return_on_capital_employed_pct"],
        "s--",
        label="ROCE %",
        color="#C55A11",
    )
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("ROE %", fontsize=8)
    ax2.set_ylabel("ROCE %", fontsize=8)
    ax.legend(fontsize=7, loc="upper left")
    ax2.legend(fontsize=7, loc="lower right")
    ax.set_title("ROE and ROCE Trend", fontsize=10)
    fig.tight_layout()
    return _chart_png(fig, path)


def bs_composition_chart(bs, path):
    d = bs.tail(10)[["year", "equity_capital", "borrowings", "other_liabilities"]].fillna(0)
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    ax.bar(d["year"], d["equity_capital"], label="Equity", color="#4472C4")
    ax.bar(
        d["year"],
        d["borrowings"],
        bottom=d["equity_capital"],
        label="Borrowings",
        color="#ED7D31",
    )
    ax.bar(
        d["year"],
        d["other_liabilities"],
        bottom=d["equity_capital"] + d["borrowings"],
        label="Other Liab.",
        color="#A5A5A5",
    )
    ax.legend(fontsize=7)
    ax.set_title("Balance Sheet Composition", fontsize=10)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout()
    return _chart_png(fig, path)


def cf_waterfall_chart(cf, path):
    latest = cf.sort_values("year").tail(1)
    if latest.empty:
        return None
    r = latest.iloc[0]
    cats = ["CFO", "CFI", "CFF", "Net Cash"]
    vals = [
        r.get("operating_activity"),
        r.get("investing_activity"),
        r.get("financing_activity"),
        r.get("net_cash_flow"),
    ]
    vals = [v if pd.notna(v) else 0 for v in vals]
    bar_colors = ["#2E7D32", "#C62828", "#ED7D31", "#4472C4"]
    fig, ax = plt.subplots(figsize=(5.2, 2.4))
    ax.bar(cats, vals, color=bar_colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Latest Year Cash Flow", fontsize=10)
    fig.tight_layout()
    return _chart_png(fig, path)


def _style():
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18, textColor=colors.white),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9, textColor=colors.white),
        "kpi_label": ParagraphStyle("kl", fontName="Helvetica", fontSize=7, textColor=colors.grey),
        "kpi_val": ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=13),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, spaceBefore=8),
        "pro": ParagraphStyle(
            "pro",
            fontName="Helvetica",
            fontSize=9,
            textColor=GREEN,
            leftIndent=8,
            bulletIndent=0,
            spaceAfter=2,
        ),
        "con": ParagraphStyle(
            "con",
            fontName="Helvetica",
            fontSize=9,
            textColor=RED,
            leftIndent=8,
            bulletIndent=0,
            spaceAfter=2,
        ),
    }


def _fmt(v, dec=1, suffix=""):
    return "N/A" if v is None or pd.isna(v) else f"{v:,.{dec}f}{suffix}"


def build_tearsheet(
    company_id: int, db_path: str = "db/nifty100.db", output_dir: str = REPORTS_DIR
) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    loaded = _load_company(engine, company_id)
    if loaded is None:
        return None
    comp, fr, pl, bs, cf = loaded

    ticker = comp["ticker"]
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    tmp = Path("output") / "_tearsheet_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    S = _style()
    latest = fr.sort_values("year").tail(1)
    r = latest.iloc[0] if not latest.empty else None

    doc = SimpleDocTemplate(
        f"{output_dir}/{ticker}_tearsheet.pdf",
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    story = []

    # ── Page 1 ──────────────────────────────────────────────────────
    header = Table(
        [
            [Paragraph(f"{comp['company_name']} ({ticker})", S["h1"])],
            [
                Paragraph(
                    f"Sector: {comp['broad_sector']} · Sub-sector: {comp['sub_sector']}",
                    S["sub"],
                )
            ],
        ],
        colWidths=[182 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 8))

    kpis = [
        ("ROE %", _fmt(r["return_on_equity_pct"] if r is not None else None)),
        (
            "ROCE %",
            _fmt(r["return_on_capital_employed_pct"] if r is not None else None),
        ),
        (
            "Net Profit Margin %",
            _fmt(r["net_profit_margin_pct"] if r is not None else None),
        ),
        ("D/E", _fmt(r["debt_to_equity"] if r is not None else None, 2)),
        ("Revenue CAGR 5y %", _fmt(r["revenue_cagr_5yr"] if r is not None else None)),
        ("FCF (Cr)", _fmt(r["free_cash_flow_cr"] if r is not None else None, 0)),
    ]
    kpi_rows = []
    for i in range(0, 6, 3):
        row = []
        for label, val in kpis[i : i + 3]:
            cell = Table([[Paragraph(label, S["kpi_label"])], [Paragraph(val, S["kpi_val"])]])
            cell.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F2F2")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            row.append(cell)
        kpi_rows.append(row)
    kpi_table = Table(kpi_rows, colWidths=[60.6 * mm] * 3)
    kpi_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    p1 = revenue_profit_chart(pl, tmp / f"{ticker}_rp.png")
    p2 = roe_roce_chart(fr, tmp / f"{ticker}_rr.png")
    charts = Table(
        [
            [
                Image(p1, width=88 * mm, height=48 * mm),
                Image(p2, width=88 * mm, height=48 * mm),
            ]
        ]
    )
    charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(charts)
    story.append(PageBreak())

    # ── Page 2 ──────────────────────────────────────────────────────
    story.append(Paragraph("Balance Sheet & Cash Flow", S["h2"]))
    p3 = bs_composition_chart(bs, tmp / f"{ticker}_bs.png")
    p4 = cf_waterfall_chart(cf, tmp / f"{ticker}_cf.png")
    chart2 = Table(
        [
            [
                Image(p3, width=88 * mm, height=46 * mm),
                Image(p4, width=88 * mm, height=46 * mm),
            ]
        ]
    )
    chart2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(chart2)
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(f"Capital Allocation: {r['capital_allocation_pattern'] or 'N/A'}", S["h2"])
    )

    # Pros & cons from the auto-generated file
    pc_path = Path("output") / "pros_cons_generated.csv"
    pros = cons = []
    if pc_path.exists():
        pc = pd.read_csv(pc_path)
        comp_pc = pc[pc["company_id"] == company_id]
        pros = comp_pc[comp_pc["type"] == "pro"]["text"].head(6).tolist()
        cons = comp_pc[comp_pc["type"] == "con"]["text"].head(6).tolist()

    story.append(Paragraph("Pros", S["h2"]))
    for p in pros or ["No pros available"]:
        story.append(Paragraph(f"<bullet>&bull;</bullet> {p}", S["pro"]))
    story.append(Paragraph("Cons", S["h2"]))
    for c in cons or ["No cons available"]:
        story.append(Paragraph(f"<bullet>&bull;</bullet> {c}", S["con"]))

    doc.build(story)
    engine.dispose()
    return f"{output_dir}/{ticker}_tearsheet.pdf"


def generate_all(db_path: str = "db/nifty100.db", output_dir: str = REPORTS_DIR):
    engine = create_engine(f"sqlite:///{db_path}")
    counts = pd.read_sql(
        text("SELECT company_id, COUNT(*) AS n FROM profitandloss GROUP BY company_id"),
        engine,
    )
    engine.dispose()

    os.makedirs("output", exist_ok=True)
    skipped = []
    generated = []
    for _, row in counts.iterrows():
        if row["n"] < 3:
            skipped.append(
                {
                    "company_id": int(row["company_id"]),
                    "reason": f"Only {row['n']} years",
                }
            )
            continue
        try:
            path = build_tearsheet(int(row["company_id"]), db_path, output_dir)
            if path:
                generated.append(path)
        except Exception as e:
            skipped.append({"company_id": int(row["company_id"]), "reason": str(e)})

    pd.DataFrame(skipped).to_csv(os.path.join(OUTPUT_DIR, "skipped_tearsheets.csv"), index=False)
    print(f"[Tearsheets] Generated {len(generated)} PDFs, skipped {len(skipped)}")
    return generated


if __name__ == "__main__":
    generate_all()
