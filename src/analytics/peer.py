"""Peer group analysis — defines peer groups, computes percentile ranks, exports Excel."""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


class PeerAnalyzer:
    """Groups companies into peer groups and ranks KPIs within each group."""

    METRICS = [
        "net_profit_margin", "operating_profit_margin", "roe", "roce",
        "roa", "debt_to_equity", "interest_coverage", "asset_turnover",
        "pe_ratio", "fcf_yield",
    ]

    def __init__(self, db_path: str = "db/nifty100.db"):
        self.db_path = Path(db_path)
        self._peer_groups: pd.DataFrame | None = None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _define_peer_groups(self) -> pd.DataFrame:
        """Assign each company to a peer group based on sector."""
        conn = self._get_conn()
        try:
            companies_df = pd.read_sql("SELECT * FROM companies", conn)
        finally:
            conn.close()

        # Use sector_name as peer group (10 sectors, ≤ 11 threshold)
        companies_df["peer_group"] = companies_df["sector_name"]
        self._peer_groups = companies_df[
            ["company_id", "sector_name", "peer_group", "market_cap"]
        ]
        return self._peer_groups

    def compute_percentiles(self, year: int | None = None) -> pd.DataFrame:
        """Compute percentile ranks for all metrics within each peer group."""
        conn = self._get_conn()
        try:
            if self._peer_groups is None:
                self._define_peer_groups()

            if year is None:
                year_row = pd.read_sql(
                    "SELECT MAX(year) as max_year FROM financial_ratios", conn
                ).iloc[0]
                year = int(year_row["max_year"])

            ratios_df = pd.read_sql(
                "SELECT * FROM financial_ratios WHERE year = ?",
                conn,
                params=[year],
            )

            if ratios_df.empty:
                return pd.DataFrame()

            merged = ratios_df.merge(
                self._peer_groups[["company_id", "peer_group"]],
                on="company_id",
                how="left",
            )
            merged["peer_group"] = merged["peer_group"].fillna("Others")

            existing_metrics = [m for m in self.METRICS if m in merged.columns]

            conn.execute("DELETE FROM peer_percentiles")
            rows_to_insert: list[tuple] = []

            for peer_group, group_df in merged.groupby("peer_group"):
                for metric in existing_metrics:
                    valid = group_df[group_df[metric].notna()].copy()
                    n = len(valid)

                    if n < 2:
                        # Not enough data — store NULL for all in group
                        for cid in group_df["company_id"]:
                            rows_to_insert.append(
                                (int(cid), int(year), metric, None, peer_group)
                            )
                        continue

                    # Compute percentile rank
                    if metric in ("debt_to_equity",):
                        # Invert: lower D/E = higher percentile
                        ranks = valid[metric].rank(method="min", ascending=False) - 1
                    else:
                        ranks = valid[metric].rank(method="min") - 1

                    valid["_pct"] = (ranks / (n - 1)) * 100
                    pct_map = dict(zip(valid["company_id"], valid["_pct"]))

                    for cid in group_df["company_id"]:
                        pct_val = pct_map.get(cid, np.nan)
                        rows_to_insert.append(
                            (
                                int(cid),
                                int(year),
                                metric,
                                float(pct_val) if pd.notna(pct_val) else None,
                                peer_group,
                            )
                        )

            if rows_to_insert:
                conn.executemany(
                    """INSERT INTO peer_percentiles
                       (company_id, year, metric_name, percentile_rank, peer_group)
                       VALUES (?, ?, ?, ?, ?)""",
                    rows_to_insert,
                )
                conn.commit()

            result_df = pd.DataFrame(
                rows_to_insert,
                columns=[
                    "company_id", "year", "metric_name",
                    "percentile_rank", "peer_group",
                ],
            )
            return result_df

        finally:
            conn.close()

    def export(self, path: str = "output/peer_comparison.xlsx") -> Path:
        """Export peer comparison to formatted Excel workbook."""
        conn = self._get_conn()
        try:
            query = """
                SELECT pp.company_id, c.ticker, c.company_name, c.sector_name,
                       pp.metric_name, pp.percentile_rank, pp.peer_group, pp.year
                FROM peer_percentiles pp
                JOIN companies c ON pp.company_id = c.company_id
                ORDER BY pp.peer_group, c.ticker, pp.metric_name
            """
            data = pd.read_sql(query, conn)
        finally:
            conn.close()

        if data.empty:
            raise ValueError(
                "No peer percentile data available. Run compute_percentiles() first."
            )

        pivot = data.pivot_table(
            index=["peer_group", "company_id", "ticker", "company_name"],
            columns="metric_name",
            values="percentile_rank",
            aggfunc="first",
        )

        for m in self.METRICS:
            if m not in pivot.columns:
                pivot[m] = np.nan
        pivot = pivot[self.METRICS]

        # ── Excel formatting ──────────────────────────────────────────
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
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        peer_groups = pivot.index.get_level_values("peer_group").unique()

        for pg in peer_groups:
            sheet_name = pg[:31]
            ws = wb.create_sheet(title=sheet_name)
            group_data = pivot.loc[pg]

            headers = ["Ticker", "Company"] + self.METRICS
            for col_idx, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", wrap_text=True)
                cell.border = thin_border

            row_num = 2
            indices = group_data.index
            if isinstance(indices, pd.MultiIndex):
                iter_data = [(idx, group_data.loc[idx]) for idx in indices]
            else:
                iter_data = [(idx, row) for idx, row in group_data.iterrows()]

            for idx, comp_row in iter_data:
                ticker = comp_row.get("ticker", idx[0] if isinstance(idx, tuple) else idx)
                co_name = comp_row.get("company_name", "")
                ws.cell(row=row_num, column=1, value=ticker).border = thin_border
                ws.cell(row=row_num, column=2, value=co_name).border = thin_border
                for m_idx, metric in enumerate(self.METRICS, 3):
                    val = comp_row.get(metric) if hasattr(comp_row, 'get') else comp_row[m_idx - 3]
                    if isinstance(val, float) and np.isnan(val):
                        val = None
                    cell = ws.cell(row=row_num, column=m_idx,
                                   value=round(float(val), 1) if val is not None else None)
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
                row_num += 1

            # Median row
            ws.cell(row=row_num, column=1, value="MEDIAN").font = median_font
            ws.cell(row=row_num, column=1).fill = median_fill
            ws.cell(row=row_num, column=1).border = thin_border
            ws.cell(row=row_num, column=2, value="").fill = median_fill
            ws.cell(row=row_num, column=2).border = thin_border
            for m_idx, metric in enumerate(self.METRICS, 3):
                vals = group_data[metric].dropna()
                median_val = vals.median() if len(vals) > 0 else None
                cell = ws.cell(
                    row=row_num, column=m_idx,
                    value=round(float(median_val), 1)
                    if median_val is not None and not pd.isna(median_val) else None,
                )
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
        print(f"[Peer] Exported to {output_path}")
        return output_path
