import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class PeerAnalyzer:
    def __init__(self, db_path="db/nifty100.db"):
        self.db_path = Path(db_path)
        self._peer_groups = None

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _define_peer_groups(self):
        conn = self._get_conn()
        try:
            companies_df = pd.read_sql("SELECT * FROM companies", conn)
        finally:
            conn.close()

        sectors = companies_df["sector_name"].dropna().unique().tolist()
        n_sectors = len(sectors)

        if n_sectors == 0:
            companies_df["peer_group"] = "All Companies"
            return companies_df

        if n_sectors <= 11:
            companies_df["peer_group"] = companies_df["sector_name"]
        else:
            sector_peer = []
            for sector in sectors:
                sector_companies = companies_df[companies_df["sector_name"] == sector]
                if len(sector_companies) <= 5:
                    sector_peer.append(sector)
                else:
                    median_mcap = sector_companies["market_cap"].median()
                    large = sector_companies["market_cap"] > median_mcap
                    sector_companies.loc[
                        sector_companies.index, "peer_group"
                    ] = sector_companies["sector_name"] + " - Large Cap"
                    sector_companies.loc[
                        sector_companies[sector_companies["market_cap"] <= median_mcap].index,
                        "peer_group",
                    ] = sector_companies["sector_name"] + " - Mid/Small Cap"
                    sector_peer.append(None)

            if any(p is not None for p in sector_peer):
                others_mask = companies_df["sector_name"].isin(
                    [s for s, p in zip(sectors, sector_peer) if p is not None]
                )
                companies_df.loc[others_mask, "peer_group"] = companies_df.loc[
                    others_mask, "sector_name"
                ]

        self._peer_groups = companies_df[["company_id", "sector_name", "peer_group", "market_cap"]]
        return self._peer_groups

    def compute_percentiles(self, year=None):
        conn = self._get_conn()
        try:
            if self._peer_groups is None:
                self._define_peer_groups()

            if year is None:
                year_row = pd.read_sql(
                    "SELECT MAX(year) as max_year FROM financial_ratios", conn
                ).iloc[0]
                year = year_row["max_year"]

            ratios_df = pd.read_sql(
                "SELECT * FROM financial_ratios WHERE year = ?",
                conn,
                params=[year],
            )

            metrics = [
                "net_profit_margin", "operating_profit_margin", "roe", "roce",
                "roa", "debt_to_equity", "interest_coverage", "asset_turnover",
                "pe_ratio", "fcf_yield",
            ]

            if ratios_df.empty:
                return pd.DataFrame()

            merged = ratios_df.merge(
                self._peer_groups[["company_id", "peer_group"]],
                on="company_id",
                how="left",
            )
            merged["peer_group"] = merged["peer_group"].fillna("Others")

            merged["icr_safe"] = merged["interest_coverage"].replace(
                [np.inf, -np.inf], np.nan
            )

            existing_metrics = [m for m in metrics if m in merged.columns]

            conn.execute("DELETE FROM peer_percentiles WHERE year = ?", [year])

            rows_to_insert = []

            for peer_group, group_df in merged.groupby("peer_group"):
                for metric in existing_metrics:
                    col = "icr_safe" if metric == "interest_coverage" else metric
                    series = group_df[col].dropna()
                    n = len(series)

                    if n < 2:
                        for cid in group_df["company_id"]:
                            rows_to_insert.append(
                                (int(cid), int(year), metric, np.nan, peer_group)
                            )
                        continue

                    ranks = series.rank(method="min") - 1
                    pct = (ranks / (n - 1)) * 100

                    if metric == "debt_to_equity":
                        pct = 100 - pct

                    for cid, val in zip(group_df["company_id"], group_df[col]):
                        if pd.isna(val) or np.isnan(val):
                            pct_val = np.nan
                        else:
                            idx = series.index.get_loc(
                                series[series.index.isin(
                                    group_df.loc[group_df["company_id"] == cid, col]
                                )].index[0]
                            )
                            pct_val = pct.iloc[idx]
                        rows_to_insert.append(
                            (int(cid), int(year), metric, float(pct_val) if pd.notna(pct_val) else None, peer_group)
                        )

            conn.executemany(
                """INSERT OR REPLACE INTO peer_percentiles
                   (company_id, year, metric_name, percentile_rank, peer_group)
                   VALUES (?, ?, ?, ?, ?)""",
                rows_to_insert,
            )
            conn.commit()

            result_df = pd.DataFrame(
                rows_to_insert,
                columns=["company_id", "year", "metric_name", "percentile_rank", "peer_group"],
            )
            return result_df

        finally:
            conn.close()

    def export(self, path="output/peer_comparison.xlsx"):
        conn = self._get_conn()
        try:
            query = """
                SELECT pp.company_id, c.ticker, c.company_name, c.sector_name,
                       pp.metric_name, pp.percentile_rank, pp.peer_group, pp.year
                FROM peer_percentiles pp
                JOIN companies c ON pp.company_id = c.company_id
                WHERE pp.year = (SELECT MAX(year) FROM peer_percentiles)
                ORDER BY pp.peer_group, c.ticker, pp.metric_name
            """
            data = pd.read_sql(query, conn)
        finally:
            conn.close()

        if data.empty:
            self.compute_percentiles()
            conn_retry = self._get_conn()
            try:
                query = """
                    SELECT pp.company_id, c.ticker, c.company_name, c.sector_name,
                           pp.metric_name, pp.percentile_rank, pp.peer_group, pp.year
                    FROM peer_percentiles pp
                    JOIN companies c ON pp.company_id = c.company_id
                    WHERE pp.year = (SELECT MAX(year) FROM peer_percentiles)
                    ORDER BY pp.peer_group, c.ticker, pp.metric_name
                """
                data = pd.read_sql(query, conn_retry)
            finally:
                conn_retry.close()

        if data.empty:
            raise ValueError("No peer percentile data available. Run compute_percentiles() first.")

        metrics = [
            "net_profit_margin", "operating_profit_margin", "roe", "roce",
            "roa", "debt_to_equity", "interest_coverage", "asset_turnover",
            "pe_ratio", "fcf_yield",
        ]

        pivot = data.pivot_table(
            index=["peer_group", "company_id", "ticker", "company_name"],
            columns="metric_name",
            values="percentile_rank",
            aggfunc="first",
        )

        for m in metrics:
            if m not in pivot.columns:
                pivot[m] = np.nan

        pivot = pivot[metrics]

        wb = Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        median_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
        median_font = Font(bold=True, italic=True)
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        peer_groups = pivot.index.get_level_values("peer_group").unique()

        for pg in peer_groups:
            sheet_name = pg[:31]
            ws = wb.create_sheet(title=sheet_name)

            group_data = pivot.loc[pg]

            headers = ["Ticker", "Company"] + metrics
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", wrap_text=True)
                cell.border = thin_border

            row = 2
            for (company_id, ticker, company_name), comp_row in group_data.iterrows():
                ws.cell(row=row, column=1, value=ticker).border = thin_border
                ws.cell(row=row, column=2, value=company_name).border = thin_border
                for m_idx, metric in enumerate(metrics, 3):
                    val = comp_row.get(metric, None)
                    if pd.isna(val) or (isinstance(val, float) and np.isnan(val)):
                        cell = ws.cell(row=row, column=m_idx, value=None)
                    else:
                        cell = ws.cell(row=row, column=m_idx, value=round(float(val), 1))
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal="center")
                    if cell.value is not None:
                        try:
                            v = float(cell.value)
                            if v >= 75:
                                cell.fill = green_fill
                            elif v <= 25:
                                cell.fill = red_fill
                            else:
                                cell.fill = yellow_fill
                        except (ValueError, TypeError):
                            pass
                row += 1

            median_row = row
            ws.cell(row=median_row, column=1, value="MEDIAN").font = median_font
            ws.cell(row=median_row, column=1).fill = median_fill
            ws.cell(row=median_row, column=1).border = thin_border
            ws.cell(row=median_row, column=2, value="").fill = median_fill
            ws.cell(row=median_row, column=2).border = thin_border
            for m_idx, metric in enumerate(metrics, 3):
                vals = group_data[metric].dropna()
                median_val = vals.median() if len(vals) > 0 else None
                cell = ws.cell(row=median_row, column=m_idx, value=round(float(median_val), 1) if median_val is not None and not pd.isna(median_val) else None)
                cell.fill = median_fill
                cell.font = median_font
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

            for col_idx in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col_idx)].width = 18
            ws.column_dimensions["A"].width = 14
            ws.column_dimensions["B"].width = 30

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)
        return output_path
