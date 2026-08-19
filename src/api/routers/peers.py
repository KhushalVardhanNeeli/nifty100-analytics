"""Peer group endpoints."""

import sqlite3

from fastapi import APIRouter, HTTPException

from src.api.db import DB_PATH, query_one

router = APIRouter(tags=["peers"])


@router.get("/peers/{group_name}")
def peers_group(group_name: str):
    check = query_one(
        "SELECT COUNT(*) AS c FROM peer_groups WHERE peer_group_name = ?", [group_name]
    )
    if not check or check["c"] == 0:
        raise HTTPException(404, "Unknown peer group")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        latest = int(conn.execute("SELECT MAX(year) FROM peer_percentiles").fetchone()[0])
        cur = conn.execute(
            """SELECT pp.company_id, c.ticker, pp.metric, pp.value, pp.percentile_rank
               FROM peer_percentiles pp JOIN companies c ON c.company_id = pp.company_id
               WHERE pp.peer_group = ? AND pp.year = ? ORDER BY c.ticker, pp.metric""",
            (group_name, latest),
        )
        rows = [dict(r) for r in cur.fetchall()]

        grouped = {}
        for r in rows:
            grouped.setdefault(r["ticker"], {})[r["metric"]] = r["percentile_rank"]
        return {
            "peer_group": group_name,
            "year": latest,
            "companies": [{"ticker": t, "percentile_ranks": m} for t, m in grouped.items()],
        }
    finally:
        conn.close()


@router.get("/companies/{ticker}/peers/compare")
def peers_compare(ticker: str):
    comp = query_one(
        "SELECT company_id, ticker, broad_sector FROM companies " "WHERE upper(ticker) = ?",
        [ticker.upper()],
    )
    if not comp:
        raise HTTPException(404, "Ticker not found")
    grp = query_one(
        "SELECT peer_group_name FROM peer_groups WHERE company_id = ?",
        [comp["company_id"]],
    )
    if not grp:
        raise HTTPException(404, "Company has no peer group assigned")

    import pandas as pd

    from src.analytics.radar import METRICS, _rank_within

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        latest = int(conn.execute("SELECT MAX(year) FROM financial_ratios").fetchone()[0])
        fr = pd.read_sql("SELECT * FROM financial_ratios WHERE year = ?", conn, params=[latest])
        peers = [
            r[0]
            for r in conn.execute(
                "SELECT company_id FROM peer_groups WHERE peer_group_name = ?",
                (grp["peer_group_name"],),
            )
        ]
    finally:
        conn.close()

    peers_df = fr[fr["company_id"].isin(peers)].copy()
    labels = [m[3] for m in METRICS]
    comp_vals, avg_vals = [], []
    for _, col, invert, _ in METRICS:
        if col not in peers_df.columns:
            comp_vals.append(None)
            avg_vals.append(None)
            continue
        ranks = _rank_within(peers_df[col], invert)
        cv = ranks.get(comp["company_id"])
        comp_vals.append(None if cv is None or pd.isna(cv) else round(float(cv), 1))
        valid = ranks[ranks.notna()]
        avg_vals.append(round(float(valid.mean()), 1) if not valid.empty else None)

    benchmark = query_one(
        "SELECT c.ticker FROM peer_groups pg JOIN companies c ON c.company_id = pg.company_id "
        "WHERE pg.peer_group_name = ? AND pg.is_benchmark = 1",
        [grp["peer_group_name"]],
    )

    return {
        "ticker": ticker,
        "peer_group": grp["peer_group_name"],
        "axes": labels,
        "company_values": comp_vals,
        "peer_average": avg_vals,
        "benchmark": benchmark["ticker"] if benchmark else None,
    }
