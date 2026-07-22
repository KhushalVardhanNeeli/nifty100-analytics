"""Cash Flow KPIs — CFO quality, CapEx intensity, FCF conversion, allocation patterns."""

import os
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")


class CashFlowAnalyzer:
    def __init__(self, pl_df=None, cf_df=None, db_path="db/nifty100.db"):
        if pl_df is not None:
            self.pl = pl_df.copy() if not pl_df.empty else pd.DataFrame()
        else:
            self.pl = pd.DataFrame()
        if cf_df is not None:
            self.cf = cf_df.copy() if not cf_df.empty else pd.DataFrame()
        else:
            self.cf = pd.DataFrame()

        self.db_path = db_path
        self._use_db = (pl_df is None and cf_df is None)
        if self._use_db:
            self.engine = create_engine(f"sqlite:///{db_path}")
        else:
            self.engine = None

    def _load_from_db(self):
        self.pl = pd.read_sql_query(
            text("SELECT * FROM profitandloss"), self.engine
        )
        self.cf = pd.read_sql_query(
            text("SELECT * FROM cashflow"), self.engine
        )

    def _resolve_col(self, df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return candidates[0]

    def analyze(self, company_id: int, year: int, row: Optional[dict] = None) -> Optional[dict]:
        """Backward-compatible analysis for a single company-year."""
        if self.cf.empty:
            return None

        oa_col = self._resolve_col(self.cf, ["operating_activities", "operating_activity"])
        ia_col = self._resolve_col(self.cf, ["investing_activities", "investing_activity"])
        fa_col = self._resolve_col(self.cf, ["financing_activities", "financing_activity"])

        cf_row = self.cf[
            (self.cf["company_id"] == company_id) & (self.cf["year"] == year)
        ]
        if cf_row.empty:
            return None

        cf_row = cf_row.iloc[0]
        oa = cf_row.get(oa_col) or 0
        ia = cf_row.get(ia_col) or 0
        fa = cf_row.get(fa_col) or 0

        fcf = oa + ia

        cfo_quality = self._calc_cfo_quality(company_id, oa)
        capex_intensity = self._calc_capex_intensity(
            ia, row.get("sales", 0) if row else 0
        )
        fcf_conversion = self._calc_fcf_conversion(
            fcf, row.get("operating_profit", 0) if row else 0
        )
        pattern = self._classify_allocation(oa, ia, fa)

        return {
            "fcf": fcf,
            "cfo_quality": cfo_quality,
            "capex_intensity": capex_intensity,
            "fcf_conversion": fcf_conversion,
            "allocation_pattern": pattern,
        }

    def _calc_cfo_quality(self, company_id: int, cfo_current: float) -> Optional[str]:
        if self.pl.empty:
            if cfo_current > 0:
                return "High Quality"
            return None

        pl_company = self.pl[self.pl["company_id"] == company_id]
        if pl_company.empty:
            return None

        pl_company = pl_company.sort_values("year", ascending=False)
        recent = pl_company.head(5)

        oa_col = self._resolve_col(self.cf, ["operating_activities", "operating_activity"])
        cf_company = self.cf[self.cf["company_id"] == company_id]
        cfo_by_year = {}
        if oa_col in cf_company.columns:
            cfo_by_year = dict(zip(cf_company["year"], cf_company[oa_col]))

        ratios = []
        for _, prow in recent.iterrows():
            yr = prow["year"]
            pat = prow.get("net_profit")
            cfo = cfo_by_year.get(yr)
            if pat and pat != 0 and cfo is not None:
                ratios.append(cfo / pat)

        if not ratios:
            if cfo_current > 0:
                return "High Quality"
            return None

        avg_ratio = sum(ratios) / len(ratios)
        if avg_ratio > 1.0:
            return "High Quality"
        elif avg_ratio >= 0.5:
            return "Moderate"
        else:
            return "Accrual Risk"

    def _calc_capex_intensity(self, investing_activity, sales) -> Optional[str]:
        if not sales or sales == 0:
            return None
        intensity = abs(investing_activity) / sales * 100
        if intensity < 3:
            return "Asset Light"
        elif intensity <= 8:
            return "Moderate"
        else:
            return "Capital Intensive"

    def _calc_fcf_conversion(self, fcf, operating_profit) -> Optional[float]:
        if not operating_profit or operating_profit == 0:
            return None
        return (fcf / operating_profit) * 100

    def _classify_allocation(self, cfo, cfi, cff) -> str:
        cfo_s = "+" if cfo > 0 else "-"
        cfi_s = "+" if cfi > 0 else "-"
        cff_s = "+" if cff > 0 else "-"

        signs = (cfo_s, cfi_s, cff_s)
        mapping = {
            ("+", "-", "-"): "Healthy Growth",
            ("+", "-", "+"): "Growth + Fundraising",
            ("+", "+", "-"): "Asset Sale / Deleveraging",
            ("+", "+", "+"): "Cash Accumulation",
            ("-", "-", "-"): "Severe Stress",
            ("-", "-", "+"): "Funding Operations",
            ("-", "+", "-"): "Restructuring",
            ("-", "+", "+"): "Survival Mode",
        }
        return mapping.get(signs, f"({cfo_s},{cfi_s},{cff_s})")

    # ── New Sprint 2 public API ──────────────────────────────────────────

    def compute(self, company_id=None):
        if self._use_db:
            self._load_from_db()

        if self.pl.empty or self.cf.empty:
            return pd.DataFrame()

        oa_col = self._resolve_col(self.cf, ["operating_activities", "operating_activity"])
        ia_col = self._resolve_col(self.cf, ["investing_activities", "investing_activity"])
        fa_col = self._resolve_col(self.cf, ["financing_activities", "financing_activity"])

        pl = self.pl.copy()
        cf = self.cf.copy()

        if company_id is not None:
            pl = pl[pl["company_id"] == company_id]
            cf = cf[cf["company_id"] == company_id]

        results = []
        unique_companies = pl["company_id"].unique()

        for cid in unique_companies:
            pl_c = pl[pl["company_id"] == cid].sort_values("year")
            cf_c = cf[cf["company_id"] == cid].sort_values("year")

            if pl_c.empty or cf_c.empty:
                continue

            # 5-year average CFO/PAT ratio
            pl_recent = pl_c.sort_values("year", ascending=False).head(5)
            cf_by_year = dict(zip(cf_c["year"], cf_c[oa_col])) if oa_col in cf_c.columns else {}

            cfo_ratios = []
            for _, prow in pl_recent.iterrows():
                yr = prow["year"]
                pat = prow.get("net_profit")
                cfo = cf_by_year.get(yr)
                if pat and pat != 0 and cfo is not None:
                    cfo_ratios.append(cfo / pat)

            if cfo_ratios:
                avg_cfo_pat = sum(cfo_ratios) / len(cfo_ratios)
                if avg_cfo_pat > 1.0:
                    cfo_quality_label = "High Quality"
                elif avg_cfo_pat >= 0.5:
                    cfo_quality_label = "Moderate"
                else:
                    cfo_quality_label = "Accrual Risk"
                cfo_quality_value = avg_cfo_pat
            else:
                neg_years = sum(
                    1 for _, prow in pl_recent.iterrows()
                    if prow.get("net_profit") is not None and prow["net_profit"] < 0
                )
                if neg_years > len(pl_recent) / 2:
                    cfo_quality_label = "Unrated (Loss-making)"
                else:
                    cfo_quality_label = "High Quality"
                cfo_quality_value = None

            # 5-year capex intensity
            capex_col = self._resolve_col(cf_c, ["capex", "investing_activities", "investing_activity"])
            sales_col = "sales"

            cf_recent = cf_c.sort_values("year", ascending=False).head(5)
            capex_ratios = []
            for _, cfrow in cf_recent.iterrows():
                yr = cfrow["year"]
                capex_val = cfrow.get(capex_col) or 0
                pl_match = pl_c[pl_c["year"] == yr]
                if not pl_match.empty and sales_col in pl_match.columns:
                    sales_val = pl_match.iloc[0][sales_col]
                    if sales_val and sales_val != 0:
                        capex_ratios.append(abs(capex_val) / sales_val)

            if capex_ratios:
                avg_capex_intensity = (sum(capex_ratios) / len(capex_ratios)) * 100
                if avg_capex_intensity < 3:
                    capex_label = "Asset Light"
                elif avg_capex_intensity <= 8:
                    capex_label = "Moderate"
                else:
                    capex_label = "Capital Intensive"
            else:
                capex_label = None

            # Process each year
            for _, cfrow in cf_c.iterrows():
                yr = int(cfrow["year"])
                oa = cfrow.get(oa_col) or 0
                ia = cfrow.get(ia_col) or 0
                fa = cfrow.get(fa_col) or 0

                pattern = self._classify_allocation(oa, ia, fa)

                pl_match = pl_c[pl_c["year"] == yr]
                net_profit_val = pl_match.iloc[0]["net_profit"] if not pl_match.empty else None

                fcf_val = oa + ia
                if net_profit_val and net_profit_val > 0:
                    fcf_conv = fcf_val / net_profit_val * 100
                else:
                    fcf_conv = None

                results.append({
                    "company_id": int(cid),
                    "year": yr,
                    "cfo_quality": cfo_quality_value,
                    "cfo_quality_label": cfo_quality_label,
                    "capex_intensity_label": capex_label,
                    "allocation_pattern": pattern,
                    "fcf_conversion": fcf_conv,
                })

        return pd.DataFrame(results)

    def _store_results(self, df: pd.DataFrame):
        if df.empty or self.engine is None:
            return

        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    text(
                        "UPDATE financial_ratios SET "
                        "cfo_quality = :cq, capex_intensity = :ci, "
                        "allocation_pattern = :ap "
                        "WHERE company_id = :cid AND year = :yr"
                    ),
                    {
                        "cq": row.get("cfo_quality"),
                        "ci": row.get("capex_intensity_label"),
                        "ap": row.get("allocation_pattern"),
                        "cid": int(row["company_id"]),
                        "yr": int(row["year"]),
                    },
                )

    def run(self):
        print("[CashFlowAnalyzer] Computing cash flow KPIs...")
        if self._use_db:
            self._load_from_db()

        results = self.compute()
        if self._use_db and not results.empty:
            self._store_results(results)

        print(f"[CashFlowAnalyzer] Processed {len(results)} rows")
        return results


if __name__ == "__main__":
    analyzer = CashFlowAnalyzer()
    analyzer.run()
