"""Portfolio summary PDF — Sprint 5 (Day 35).

One page per company (alphabetical by ticker) with the top 6 KPIs and
trend arrows (up if the metric improved YoY, down if it declined,
right if flat within 2%).
"""

import os
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)
from sqlalchemy import create_engine, text

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
REPORTS_DIR = "reports/portfolio"

KPIS = [
    ("ROE %", "return_on_equity_pct"),
    ("ROCE %", "return_on_capital_employed_pct"),
    ("NPM %", "net_profit_margin_pct"),
    ("D/E", "debt_to_equity"),
    ("Rev CAGR 5y %", "revenue_cagr_5yr"),
    ("FCF (Cr)", "free_cash_flow_cr"),
]


def _arrow(now, prev, invert=False):
    if now is None or prev is None or pd.isna(now) or pd.isna(prev):
        return "—"
    diff = now - prev
    scale = abs(prev) if prev != 0 else abs(now)
    pct = diff / scale if scale else 0
    if invert:
        pct = -pct
    if pct > 0.02:
        return "▲"
    if pct < -0.02:
        return "▼"
    return "→"


def build_portfolio(db_path: str = "db/nifty100.db", output_dir: str = REPORTS_DIR) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    latest = int(pd.read_sql(text("SELECT MAX(year) AS y FROM financial_ratios"), engine).iloc[0]["y"])
    companies = pd.read_sql(text("SELECT company_id, ticker, company_name, broad_sector FROM companies"),
                            engine).sort_values("ticker")
    fr = pd.read_sql(text("SELECT * FROM financial_ratios WHERE year IN (:a, :b)"),
                     engine, params={"a": latest, "b": latest - 1})
    engine.dispose()

    now = fr[fr["year"] == latest].set_index("company_id")
    prev = fr[fr["year"] == latest - 1].set_index("company_id")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(f"{output_dir}/portfolio_summary.pdf", pagesize=A4,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor("#1F3864"))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, textColor=colors.white)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9)

    story = [Paragraph("Nifty 100 Portfolio Summary", h1),
             Paragraph(f"Latest year: {latest}", body), Spacer(1, 10)]

    for _, c in companies.iterrows():
        cid = int(c["company_id"])
        if cid not in now.index:
            continue
        cur = now.loc[cid]
        prv = prev.loc[cid] if cid in prev.index else pd.Series(dtype=float)

        head = Table([[Paragraph(f"{c['company_name']} ({c['ticker']})", h2)]],
                     colWidths=[182 * mm])
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1F3864")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(head)

        rows = [["Metric", "Latest", "Arrow"]]
        for label, col in KPIS:
            cur_v = cur.get(col)
            prev_v = prv.get(col) if not prv.empty else None
            invert = col in ("debt_to_equity",)
            rows.append([label, "N/A" if cur_v is None or pd.isna(cur_v) else f"{float(cur_v):,.1f}",
                         _arrow(cur_v, prev_v, invert)])

        t = Table(rows, colWidths=[50 * mm, 60 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(Spacer(1, 4))
        story.append(t)
        story.append(Spacer(1, 6))
        story.append(PageBreak())

    out = f"{output_dir}/portfolio_summary.pdf"
    doc.build(story)
    print(f"[Portfolio] Built {out}")
    return out


if __name__ == "__main__":
    build_portfolio()
