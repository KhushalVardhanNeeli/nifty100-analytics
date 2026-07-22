import yaml
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class ScreenerEngine:
    def __init__(self, config_path="config/screener_config.yaml", db_path="db/nifty100.db"):
        self.config_path = Path(config_path)
        self.db_path = Path(db_path)

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.presets = self.config["presets"]
        self._df = None
        self._companies_df = None

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_data(self):
        conn = self._get_conn()
        try:
            self._companies_df = pd.read_sql("SELECT * FROM companies", conn)

            latest_year_query = "SELECT MAX(year) as max_year FROM financial_ratios"
            latest_year = pd.read_sql(latest_year_query, conn).iloc[0]["max_year"]

            ratios_df = pd.read_sql(
                "SELECT * FROM financial_ratios WHERE year = ?",
                conn,
                params=[latest_year],
            )

            self._df = ratios_df.merge(
                self._companies_df, on="company_id", how="left"
            )

            self._compute_cagrs(conn, latest_year)

            self._latest_year = latest_year
        finally:
            conn.close()
        return self._df

    def _compute_cagrs(self, conn, latest_year):
        pl_query = """
            SELECT company_id, year, sales, net_profit
            FROM profitandloss
            ORDER BY company_id, year
        """
        pl_df = pd.read_sql(pl_query, conn)

        if pl_df.empty:
            self._df["revenue_cagr_3y"] = np.nan
            self._df["revenue_cagr_5y"] = np.nan
            self._df["pat_cagr_3y"] = np.nan
            self._df["pat_cagr_5y"] = np.nan
            return

        cagr_data = []
        for company_id, group in pl_df.groupby("company_id"):
            group = group.sort_values("year")
            years = group["year"].values
            sales = group["sales"].values
            profits = group["net_profit"].values

            cagrs = {"company_id": company_id}

            for period_label, period in [("3y", 3), ("5y", 5)]:
                start_year = latest_year - period

                if start_year in years[len(xtuple := np.where(years == start_year)[0]) > 0]:
                    continue

                mask_start = years == start_year
                mask_end = years == latest_year

                start_idx = np.where(years == start_year)[0]
                end_idx = np.where(years == latest_year)[0]

                if len(start_idx) > 0 and len(end_idx) > 0:
                    start_i = start_idx[0]
                    end_i = end_idx[0]
                    if sales[start_i] > 0:
                        cagrs[f"revenue_cagr_{period_label}"] = (
                            (sales[end_i] / sales[start_i]) ** (1.0 / period) - 1
                        ) * 100
                    else:
                        cagrs[f"revenue_cagr_{period_label}"] = np.nan

                    if profits[start_i] > 0:
                        cagrs[f"pat_cagr_{period_label}"] = (
                            (profits[end_i] / profits[start_i]) ** (1.0 / period) - 1
                        ) * 100
                    else:
                        cagrs[f"pat_cagr_{period_label}"] = np.nan
                else:
                    cagrs[f"revenue_cagr_{period_label}"] = np.nan
                    cagrs[f"pat_cagr_{period_label}"] = np.nan

            cagr_data.append(cagrs)

        if cagr_data:
            cagr_df = pd.DataFrame(cagr_data)
            self._df = self._df.merge(cagr_df, on="company_id", how="left")
        else:
            for col in ["revenue_cagr_3y", "revenue_cagr_5y", "pat_cagr_3y", "pat_cagr_5y"]:
                self._df[col] = np.nan

    def _is_financial_sector(self, sector_name):
        if sector_name is None:
            return False
        sector_lower = str(sector_name).lower()
        financial_keywords = [
            "financial", "bank", "insurance", "nbfc", "finance",
            "asset management", "broking", "capital markets",
        ]
        return any(kw in sector_lower for kw in financial_keywords)

    def apply_filters(self, df, preset_name):
        preset = self.presets[preset_name]
        exclude_financials_for = preset.get("exclude_financials_for", [])
        mask = pd.Series(True, index=df.index)

        for f in preset["filters"]:
            metric = f["metric"]
            min_val = f.get("min")
            max_val = f.get("max")
            operator = f.get("operator")
            value = f.get("value")
            treat_debt_free = f.get("treat_debt_free", False)

            if metric not in df.columns:
                continue

            if operator == "equals":
                filter_mask = df[metric] == value
            elif min_val is not None and max_val is not None:
                filter_mask = (df[metric] >= min_val) & (df[metric] <= max_val)
            elif min_val is not None:
                filter_mask = df[metric] >= min_val
            elif max_val is not None:
                filter_mask = df[metric] <= max_val
            else:
                continue

            if treat_debt_free and metric == "interest_coverage":
                df_metric = df[metric]
                debt_free_mask = df_metric.isna() | (df_metric == 0)
                if min_val is not None:
                    filter_mask = filter_mask | debt_free_mask
                continue

            if metric in exclude_financials_for and "sector_name" in df.columns:
                financial_mask = df["sector_name"].apply(self._is_financial_sector)
                effective_mask = filter_mask | financial_mask
            else:
                effective_mask = filter_mask

            mask = mask & effective_mask

        return df[mask]

    def composite_score(self, df):
        result = df.copy()

        profit_metrics = ["roe", "net_profit_margin", "operating_profit_margin"]
        cash_metrics = ["cfo_quality", "fcf_yield"]
        growth_metrics = [
            "revenue_cagr_3y", "revenue_cagr_5y", "pat_cagr_3y", "pat_cagr_5y"
        ]
        leverage_metrics = ["debt_to_equity", "interest_coverage"]

        cfo_quality_map = {
            "High Quality": 100,
            "Moderate": 60,
            "Accrual Risk": 30,
            "Unrated": 50,
        }

        for col in profit_metrics:
            if col not in result.columns:
                result[col] = np.nan

        for col in cash_metrics:
            if col not in result.columns:
                result[col] = np.nan

        for col in growth_metrics:
            if col not in result.columns:
                result[col] = np.nan

        for col in leverage_metrics:
            if col not in result.columns:
                result[col] = np.nan

        def winsorize(series, lower=0.10, upper=0.90):
            s = series.dropna()
            if len(s) < 5:
                return series
            lo = s.quantile(lower)
            hi = s.quantile(upper)
            return series.clip(lo, hi)

        def percentile_rank(series):
            s = series.dropna()
            if len(s) < 2:
                return pd.Series(np.nan, index=series.index)
            ranks = s.rank(pct=False)
            n = len(s)
            result = (ranks - 1) / (n - 1) * 100
            return result.reindex(series.index)

        profit_scores = pd.DataFrame(index=result.index)
        for col in profit_metrics:
            if col in result.columns:
                wins = winsorize(result[col])
                profit_scores[col] = percentile_rank(wins)

        valid_profit = profit_scores.count(axis=1)
        profitability = profit_scores.mean(axis=1)
        profitability[valid_profit == 0] = np.nan

        cash_scores = pd.DataFrame(index=result.index)
        if "cfo_quality" in result.columns:
            cash_scores["cfo_quality_num"] = result["cfo_quality"].map(
                cfo_quality_map
            ).fillna(50)
            cash_scores["cfo_quality_num"] = cash_scores["cfo_quality_num"].clip(0, 100)
        else:
            cash_scores["cfo_quality_num"] = 50

        if "fcf_yield" in result.columns:
            wins = winsorize(result["fcf_yield"])
            cash_scores["fcf_yield_pct"] = percentile_rank(wins)

        valid_cash = cash_scores.count(axis=1)
        cash_quality = cash_scores.mean(axis=1)
        cash_quality[valid_cash == 0] = np.nan

        growth_scores = pd.DataFrame(index=result.index)
        for col in growth_metrics:
            if col in result.columns:
                wins = winsorize(result[col])
                growth_scores[col] = percentile_rank(wins)

        valid_growth = growth_scores.count(axis=1)
        growth = growth_scores.mean(axis=1)
        growth[valid_growth == 0] = np.nan

        leverage_scores = pd.DataFrame(index=result.index)
        if "debt_to_equity" in result.columns:
            wins = winsorize(result["debt_to_equity"])
            de_pct = percentile_rank(wins)
            leverage_scores["de_inv"] = 100 - de_pct

        if "interest_coverage" in result.columns:
            icr = result["interest_coverage"].copy()
            icr.replace([np.inf, -np.inf], np.nan, inplace=True)
            wins = winsorize(icr)
            leverage_scores["icr_pct"] = percentile_rank(wins)

        valid_lev = leverage_scores.count(axis=1)
        leverage = leverage_scores.mean(axis=1)
        leverage[valid_lev == 0] = np.nan

        weights = self.presets.get("composite_weights", {
            "profitability": 0.35,
            "cash_quality": 0.30,
            "growth": 0.20,
            "leverage": 0.15,
        })

        composite = (
            profitability * weights.get("profitability", 0.35) +
            cash_quality * weights.get("cash_quality", 0.30) +
            growth * weights.get("growth", 0.20) +
            leverage * weights.get("leverage", 0.15)
        )

        result["composite_score"] = composite

        return result

    def screen(self, preset_name):
        if preset_name not in self.presets:
            available = list(self.presets.keys())
            raise ValueError(
                f"Unknown preset '{preset_name}'. Available: {available}"
            )

        df = self.load_data()
        filtered = self.apply_filters(df, preset_name)

        if filtered.empty:
            return filtered

        preset = self.presets[preset_name]
        self.presets = {"_current": preset}
        scored = self.composite_score(filtered)
        self.presets = self.config["presets"]

        sort_by = preset.get("sort_by", "composite_score")
        sort_order = preset.get("sort_order", "desc")
        ascending = sort_order != "desc"

        if sort_by in scored.columns:
            scored = scored.sort_values(sort_by, ascending=ascending)

        return scored

    def export(self, preset_name):
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        result = self.screen(preset_name)

        output_path = output_dir / "screener_output.xlsx"

        if output_path.exists():
            wb = self._load_or_create_workbook(output_path)
        else:
            wb = Workbook()
            if "Sheet" in wb.sheetnames:
                del wb["Sheet"]

        sheet_name = preset_name[:31]

        if sheet_name in wb.sheetnames:
            del wb[sheet_name]

        ws = wb.create_sheet(title=sheet_name)

        self._write_df_to_sheet(ws, result)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)

    def run_all(self):
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "screener_output.xlsx"

        wb = Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

        for preset_name in self.presets:
            try:
                result = self.screen(preset_name)
                sheet_name = preset_name[:31]
                ws = wb.create_sheet(title=sheet_name)
                self._write_df_to_sheet(ws, result)
            except Exception as e:
                ws = wb.create_sheet(title=preset_name[:31])
                ws["A1"] = f"Error: {e}"

        wb.save(output_path)
        return output_path

    def _load_or_create_workbook(self, path):
        from openpyxl import load_workbook
        try:
            return load_workbook(path)
        except Exception:
            wb = Workbook()
            if "Sheet" in wb.sheetnames:
                del wb["Sheet"]
            return wb

    def _write_df_to_sheet(self, ws, df):
        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        display_df = df.copy()
        for col in display_df.select_dtypes(include=["float64", "float32"]).columns:
            display_df[col] = display_df[col].apply(
                lambda x: round(x, 2) if pd.notna(x) else x
            )

        for col_idx, col_name in enumerate(display_df.columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            cell.border = thin_border

        for row_idx, (_, row) in enumerate(display_df.iterrows(), 2):
            for col_idx, col_name in enumerate(display_df.columns, 1):
                val = row[col_name]
                if isinstance(val, float) and (pd.isna(val) or np.isnan(val)):
                    val = None
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

        if "composite_score" in df.columns:
            comp_col_idx = list(display_df.columns).index("composite_score") + 1
            for row_idx in range(2, len(display_df) + 2):
                cell = ws.cell(row=row_idx, column=comp_col_idx)
                if cell.value is not None:
                    try:
                        score = float(cell.value)
                        if score >= 70:
                            cell.fill = green_fill
                        elif score < 30:
                            cell.fill = red_fill
                        else:
                            cell.fill = yellow_fill
                    except (ValueError, TypeError):
                        pass

        for col_idx in range(1, len(display_df.columns) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16
