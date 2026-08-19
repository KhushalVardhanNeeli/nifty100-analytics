"""Sector report PDFs — Sprint 5 (Day 34).

One PDF per broad_sector (11) saved to reports/sector/{sector}_report.pdf.
Each contains a median-KPI summary page plus a company table (8 metrics each).
"""

import os
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import create_engine, text

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
REPORTS_DIR = "reports/sector"

METRICS = [
    ("ROE %", "return_on_equity_pct"),
    ("ROCE %", "return_on_capital_employed_pct"),
    ("NPM %", "net_profit_margin_pct"),
    ("D/E", "debt_to_equity"),
    ("ICR", "interest_coverage"),
    ("Rev CAGR 5y %", "revenue_cagr_5yr"),
    ("PAT CAGR 5y %", "pat_cagr_5yr"),
    ("Asset Turnover", "asset_turnover"),
]


def _fmt(v, dec=1):
    return "N/A" if v is None or pd.isna(v) else f"{v:,.{dec}f}"


def build_sector_report(
    sector: str, db_path: str = "db/nifty100.db", output_dir: str = REPORTS_DIR
) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    latest = int(
        pd.read_sql(text("SELECT MAX(year) AS y FROM financial_ratios"), engine).iloc[0]["y"]
    )
    companies = pd.read_sql(
        text("SELECT company_id, ticker, company_name, broad_sector FROM companies"),
        engine,
    )
    fr = pd.read_sql(
        text("SELECT * FROM financial_ratios WHERE year = :y"),
        engine,
        params={"y": latest},
    )
    engine.dispose()

    members = companies[companies["broad_sector"] == sector]
    data = members.merge(fr, on="company_id", how="left")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fname = sector.replace(" ", "_")
    doc = SimpleDocTemplate(
        f"{output_dir}/{fname}_report.pdf",
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    h1 = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#1F3864"),
    )
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, spaceBefore=10)

    story = [Paragraph(f"{sector} Sector Report ({latest})", h1), Spacer(1, 8)]

    # Median KPIs
    med_cols = [col for _, col in METRICS]
    med = data[med_cols].median() if not data.empty else pd.Series(dtype=float)
    med_rows = [["Metric", "Median"]]
    for label, col in METRICS:
        med_rows.append([label, _fmt(med.get(col))])
    mt = Table(med_rows, colWidths=[40 * mm, 30 * mm])
    mt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]
        )
    )
    story.append(Paragraph("Sector Summary — Median KPIs", h2))
    story.append(mt)
    story.append(Spacer(1, 10))

    # Company table
    header = ["Ticker", "Company"] + [label for label, _ in METRICS]
    rows = [header]
    for _, r in data.sort_values("ticker").iterrows():
        rows.append([r["ticker"], r["company_name"]] + [_fmt(r[col]) for _, col in METRICS])

    ct = Table(rows, repeatRows=1)
    ct.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F2F2F2")],
                ),
            ]
        )
    )
    story.append(Paragraph(f"Companies in {sector} ({len(data)})", h2))
    story.append(ct)

    doc.build(story)
    return f"{output_dir}/{fname}_report.pdf"


def generate_all(db_path: str = "db/nifty100.db", output_dir: str = REPORTS_DIR):
    engine = create_engine(f"sqlite:///{db_path}")
    sectors = pd.read_sql(
        text("SELECT DISTINCT broad_sector FROM companies " "WHERE broad_sector IS NOT NULL"),
        engine,
    )["broad_sector"].tolist()
    engine.dispose()
    generated = [build_sector_report(s, db_path, output_dir) for s in sectors]
    print(f"[Sector] Generated {len(generated)} sector reports")
    return generated


if __name__ == "__main__":
    generate_all()
