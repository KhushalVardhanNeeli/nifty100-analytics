"""Auto Pros/Cons generator — Sprint 5 (Day 30).

Evaluates 12 pro rules and 12 con rules per company using the ratio engine
outputs and raw statements. Rules with confidence > 60 are written to
output/pros_cons_generated.csv. Every company is guaranteed at least one
pro and one con.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")


def _streak(series: list) -> int:
    """Number of consecutive final entries satisfying the predicate."""
    n = 0
    for v in reversed(series):
        if v:
            n += 1
        else:
            break
    return n


class ProsConsGenerator:
    """Evaluates pro/con rules against each company's metrics."""

    def _load(self, db_path: str) -> dict:
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            companies = pd.read_sql(text("SELECT company_id, ticker, company_name, broad_sector "
                                         "FROM companies"), engine)
            fr = pd.read_sql(text("SELECT * FROM financial_ratios ORDER BY company_id, year"), engine)
            pl = pd.read_sql(text("SELECT company_id, year, sales, net_profit, eps, "
                                  "operating_profit, depreciation, dividend_payout "
                                  "FROM profitandloss ORDER BY company_id, year"), engine)
            mc = pd.read_sql(text("SELECT company_id, year, dividend_yield_pct "
                                  "FROM market_cap"), engine)
        finally:
            engine.dispose()

        cid2ticker = dict(zip(companies["company_id"], companies["ticker"]))
        cid2sector = dict(zip(companies["company_id"], companies["broad_sector"]))

        metrics = {}
        for cid in companies["company_id"]:
            frc = fr[fr["company_id"] == cid].sort_values("year")
            plc = pl[pl["company_id"] == cid].sort_values("year")
            mcc = mc[mc["company_id"] == cid].sort_values("year")

            def series(col, df):
                return df.dropna(subset=[col])[col].tolist()

            def latest(col, df):
                s = df.dropna(subset=[col])
                return s.iloc[-1][col] if not s.empty else None

            is_fin = "financial" in str(cid2sector.get(cid, "")).lower()
            metrics[int(cid)] = {
                "ticker": cid2ticker.get(cid),
                "sector": cid2sector.get(cid),
                "is_fin": is_fin,
                "roe": latest("return_on_equity_pct", frc),
                "roe_series": series("return_on_equity_pct", frc),
                "roce": latest("return_on_capital_employed_pct", frc),
                "npm": latest("net_profit_margin_pct", frc),
                "opm": latest("operating_profit_margin_pct", frc),
                "opm_series": series("operating_profit_margin_pct", frc),
                "de": latest("debt_to_equity", frc),
                "de_series": series("debt_to_equity", frc),
                "icr": latest("interest_coverage", frc),
                "icr_label": latest("icr_label", frc),
                "fcf": latest("free_cash_flow_cr", frc),
                "fcf_series": series("free_cash_flow_cr", frc),
                "net_debt": latest("net_debt_cr", frc),
                "rev_cagr5": latest("revenue_cagr_5yr", frc),
                "pat_cagr5": latest("pat_cagr_5yr", frc),
                "eps_cagr5": latest("eps_cagr_5yr", frc),
                "sales": latest("sales", plc),
                "sales_series": series("sales", plc),
                "net_profit": latest("net_profit", plc),
                "eps": latest("eps", plc),
                "eps_series": series("eps", plc),
                "op": latest("operating_profit", plc),
                "depreciation": latest("depreciation", plc),
                "div_payout": latest("dividend_payout", plc),
                "div_yield": latest("dividend_yield_pct", mcc),
            }
        return metrics

    def _conf(self, base: float, boost: float = 0.0) -> float:
        return min(100.0, base + boost)

    # ── Pro rules ──────────────────────────────────────────────────────

    def _pro_rules(self, m):
        out = []

        if m["roe"] is not None and m["roe"] > 20 and len(m["roe_series"]) >= 3 and all(
                r > 20 for r in m["roe_series"][-3:]):
            out.append((1, "Consistently high return on equity above 20% demonstrates exceptional capital efficiency",
                        self._conf(80, min(m["roe"] - 20, 15))))
        if len(m["fcf_series"]) >= 5 and all(f > 0 for f in m["fcf_series"][-5:]):
            out.append((2, "Strong free cash flow generation over 5 years signals healthy business fundamentals",
                        self._conf(80)))
        if m["de"] == 0:
            out.append((3, "Debt-free balance sheet provides financial flexibility and eliminates interest burden",
                        self._conf(82)))
        if m["rev_cagr5"] is not None and m["rev_cagr5"] > 15:
            out.append((4, "Revenue growing at above 15% CAGR over 5 years reflects strong business momentum",
                        self._conf(78, min(m["rev_cagr5"] - 15, 12))))
        if m["opm"] is not None and m["opm"] > 25:
            out.append((5, "Operating profit margin above 25% indicates strong pricing power and cost discipline",
                        self._conf(76, min(m["opm"] - 25, 10))))
        if m["pat_cagr5"] is not None and m["pat_cagr5"] > 20:
            out.append((6, "Net profit compounding at above 20% over 5 years creates significant shareholder value",
                        self._conf(78, min(m["pat_cagr5"] - 20, 12))))
        if m["icr_label"] == "Debt Free" or (m["icr"] is not None and m["icr"] > 10):
            out.append((7, "Very high interest coverage ratio reflects negligible financial stress from debt servicing",
                        self._conf(75)))
        if m["div_yield"] is not None and m["div_yield"] > 2 and m["fcf"] is not None and m["fcf"] > 0:
            out.append((8, "Consistent dividend yield above 2% backed by positive free cash flow",
                        self._conf(75)))
        if m["eps_cagr5"] is not None and m["eps_cagr5"] > 15:
            out.append((9, "Earnings per share growing above 15% CAGR indicates strong earnings quality and compounding",
                        self._conf(77, min(m["eps_cagr5"] - 15, 12))))
        if len(m["roe_series"]) >= 4 and m["roe_series"][-1] > m["roe_series"][-2] > m["roe_series"][-3]:
            out.append((10, "Return on equity improving for 3 consecutive years shows strengthening business quality",
                        self._conf(74)))
        if m["rev_cagr5"] is not None and m["pat_cagr5"] is not None and m["rev_cagr5"] < m["pat_cagr5"]:
            out.append((11, "Revenue growing slower than profits shows improving operating leverage and scale benefits",
                        self._conf(72)))
        if m["op"] is not None and m["depreciation"] is not None:
            ebitda = m["op"] + m["depreciation"]
            if m["net_debt"] is not None and ebitda > 0 and m["net_debt"] / ebitda < 1.0:
                out.append((12, "Growing asset base funded by internal accruals reflects self-sustaining growth",
                            self._conf(70)))

        return [(r_id, text, conf) for r_id, text, conf in out if conf > 60]

    def _con_rules(self, m):
        out = []

        if m["de"] is not None and m["de"] > 2 and not m["is_fin"]:
            out.append((1, f"Debt-to-equity ratio of {m['de']:.2f} is elevated for a non-financial company and warrants monitoring",
                        self._conf(76, min((m["de"] - 2) * 5, 14))))
        if len(m["fcf_series"]) >= 3 and all(f < 0 for f in m["fcf_series"][-3:]):
            out.append((2, "Free cash flow negative for 3 consecutive years raises concern about cash generation quality",
                        self._conf(78)))
        if len(m["opm_series"]) >= 4 and m["opm_series"][-1] < m["opm_series"][-2] < m["opm_series"][-3] < m["opm_series"][-4]:
            out.append((3, "Operating margins declining for 3 consecutive years suggest pricing or cost pressure",
                        self._conf(74)))
        if m["net_profit"] is not None and m["net_profit"] < 0:
            out.append((4, "Company reported a net loss in the most recent financial year",
                        self._conf(80)))
        if len(m["sales_series"]) >= 3 and m["sales_series"][-1] < m["sales_series"][-2] < m["sales_series"][-3]:
            out.append((5, "Revenue contraction over 2 consecutive years indicates demand weakness or market share loss",
                        self._conf(76)))
        if m["icr"] is not None and m["icr"] < 1.5 and m["icr_label"] != "Debt Free":
            out.append((6, "Interest coverage ratio below 1.5x indicates the company is at risk of not meeting its debt obligations",
                        self._conf(78)))
        if m["div_payout"] is not None and m["div_payout"] > 100:
            out.append((7, "Dividend payout ratio above 100% means the company is paying dividends from reserves, which is unsustainable",
                        self._conf(74)))
        if len(m["de_series"]) >= 4 and m["de_series"][-1] > m["de_series"][-2] > m["de_series"][-3] > m["de_series"][-4]:
            out.append((8, "Rising debt-to-equity ratio over 3 years suggests increasing financial leverage risk",
                        self._conf(72)))
        if len(m["eps_series"]) >= 4 and m["eps_series"][-1] < m["eps_series"][-2] < m["eps_series"][-3] < m["eps_series"][-4]:
            out.append((9, "Earnings per share declining for 3 consecutive years reflects deteriorating profitability",
                        self._conf(74)))
        if m["roce"] is not None and m["roce"] < 10:
            out.append((10, "Return on capital employed below 10% suggests the business is not generating sufficient returns on invested capital",
                        self._conf(70)))
        if m["op"] is not None and m["depreciation"] is not None:
            ebitda = m["op"] + m["depreciation"]
            if m["net_debt"] is not None and ebitda > 0 and m["net_debt"] > 3 * ebitda:
                out.append((11, "Net debt exceeding 3 times EBITDA is a high leverage ratio and limits financial flexibility",
                            self._conf(75)))
        if m["rev_cagr5"] is not None and m["rev_cagr5"] < 5:
            out.append((12, "Revenue growing at below 5% over 5 years lags inflation and suggests limited business momentum",
                        self._conf(70)))

        return [(r_id, text, conf) for r_id, text, conf in out if conf > 60]

    def compute(self, db_path: str = DB_PATH) -> pd.DataFrame:
        metrics = self._load(db_path)
        rows = []
        for cid, m in metrics.items():
            pros = self._pro_rules(m)
            cons = self._con_rules(m)
            for r_id, text, conf in pros:
                rows.append({"company_id": cid, "type": "pro", "rule_id": f"PRO-{r_id}",
                             "text": text, "confidence_pct": round(conf)})
            for r_id, text, conf in cons:
                rows.append({"company_id": cid, "type": "con", "rule_id": f"CON-{r_id}",
                             "text": text, "confidence_pct": round(conf)})

            # Guarantee at least one pro and one con per company
            if not pros:
                rows.append({"company_id": cid, "type": "pro", "rule_id": "PRO-0",
                             "text": "Company maintains a presence in the Nifty 100 universe",
                             "confidence_pct": 65})
            if not cons:
                rows.append({"company_id": cid, "type": "con", "rule_id": "CON-0",
                             "text": "Company performance should be monitored for consistency",
                             "confidence_pct": 65})

        df = pd.DataFrame(rows)
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        df.to_csv(os.path.join(OUTPUT_DIR, "pros_cons_generated.csv"), index=False)
        print(f"[NLP] Generated {len(df)} pros/cons rows for {df['company_id'].nunique()} companies")
        return df


if __name__ == "__main__":
    ProsConsGenerator().compute()
