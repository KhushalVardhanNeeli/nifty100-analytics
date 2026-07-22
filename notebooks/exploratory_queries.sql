-- ═══════════════════════════════════════════════════════════════
-- Nifty 100 Financial Analytics — Exploratory SQL Queries
-- Database: db/nifty100.db (SQLite)
-- ═══════════════════════════════════════════════════════════════

-- ── Query 1: Row counts for all 10 tables ──────────────────────
-- Purpose: Quick data-volume survey to confirm data loaded correctly.
SELECT 'companies'        AS table_name, COUNT(*) AS row_count FROM companies
UNION ALL
SELECT 'sectors',          COUNT(*) FROM sectors
UNION ALL
SELECT 'profitandloss',    COUNT(*) FROM profitandloss
UNION ALL
SELECT 'balancesheet',     COUNT(*) FROM balancesheet
UNION ALL
SELECT 'cashflow',         COUNT(*) FROM cashflow
UNION ALL
SELECT 'stock_prices',     COUNT(*) FROM stock_prices
UNION ALL
SELECT 'analysis',         COUNT(*) FROM analysis
UNION ALL
SELECT 'documents',        COUNT(*) FROM documents
UNION ALL
SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL
SELECT 'peer_percentiles', COUNT(*) FROM peer_percentiles
ORDER BY table_name;

-- ── Query 2: Sector distribution (count of companies per sector) ──
-- Purpose: Understand how many companies fall into each sector bucket.
SELECT
    s.sector_name,
    COUNT(c.company_id) AS company_count
FROM sectors s
LEFT JOIN companies c ON c.sector_id = s.sector_id
GROUP BY s.sector_name
ORDER BY company_count DESC;

-- ── Query 3: Year coverage (min / max year per table that has a year column) ──
-- Purpose: Verify temporal coverage across fact tables.
SELECT 'profitandloss'    AS table_name, MIN(year) AS min_year, MAX(year) AS max_year FROM profitandloss
UNION ALL
SELECT 'balancesheet',     MIN(year), MAX(year) FROM balancesheet
UNION ALL
SELECT 'cashflow',         MIN(year), MAX(year) FROM cashflow
UNION ALL
SELECT 'analysis',         MIN(year), MAX(year) FROM analysis
UNION ALL
SELECT 'financial_ratios', MIN(year), MAX(year) FROM financial_ratios
UNION ALL
SELECT 'peer_percentiles', MIN(year), MAX(year) FROM peer_percentiles
ORDER BY table_name;

-- ── Query 4: FK integrity check — companies in P&L without a matching company_id in companies ──
-- Purpose: Catch orphan rows before they skew analytics.
SELECT DISTINCT p.company_id
FROM profitandloss p
LEFT JOIN companies c ON p.company_id = c.company_id
WHERE c.company_id IS NULL
ORDER BY p.company_id;

-- ── Query 5: Top 10 companies by market cap ──
-- Purpose: Identify the index heavyweights.
SELECT
    company_id,
    ticker,
    company_name,
    market_cap
FROM companies
WHERE market_cap IS NOT NULL
ORDER BY market_cap DESC
LIMIT 10;

-- ── Query 6: Average OPM by sector (most recent year) ──
-- Purpose: Compare sector-wise operating profitability.
SELECT
    c.sector_name,
    ROUND(AVG(p.operating_profit_margin), 2) AS avg_opm_pct,
    COUNT(DISTINCT p.company_id)              AS company_count
FROM profitandloss p
JOIN companies c ON p.company_id = c.company_id
WHERE p.year = (SELECT MAX(year) FROM profitandloss)
  AND p.operating_profit_margin IS NOT NULL
GROUP BY c.sector_name
ORDER BY avg_opm_pct DESC;

-- ── Query 7: Companies with no stock price data ──
-- Purpose: Identify companies missing in the stock_prices table.
SELECT
    c.company_id,
    c.ticker,
    c.company_name
FROM companies c
LEFT JOIN stock_prices sp ON c.company_id = sp.company_id
WHERE sp.sp_id IS NULL
ORDER BY c.ticker;

-- ── Query 8: Aggregate trends by year (avg net_profit, avg revenue, avg ROE) ──
-- Purpose: Spot macro-level trends across the Nifty 100 universe.
SELECT
    p.year,
    ROUND(AVG(p.net_profit), 2)        AS avg_net_profit,
    ROUND(AVG(p.total_revenue), 2)     AS avg_revenue,
    ROUND(AVG(fr.roe), 2)              AS avg_roe,
    COUNT(DISTINCT p.company_id)       AS companies_reported
FROM profitandloss p
LEFT JOIN financial_ratios fr ON p.company_id = fr.company_id AND p.year = fr.year
WHERE p.net_profit IS NOT NULL
GROUP BY p.year
ORDER BY p.year;

-- ── Query 9: Companies with consistent (5+ consecutive years) revenue growth ──
-- Purpose: Identify compounding-growth stories.
WITH ordered AS (
    SELECT
        company_id,
        year,
        total_revenue,
        LAG(total_revenue) OVER (PARTITION BY company_id ORDER BY year) AS prev_revenue
    FROM profitandloss
    WHERE total_revenue IS NOT NULL
),
growth_flags AS (
    SELECT
        company_id,
        year,
        total_revenue,
        prev_revenue,
        CASE WHEN total_revenue > prev_revenue THEN 1 ELSE 0 END AS grew
    FROM ordered
    WHERE prev_revenue IS NOT NULL
),
streak_groups AS (
    SELECT
        company_id,
        year,
        grew,
        year - ROW_NUMBER() OVER (PARTITION BY company_id, grew ORDER BY year) AS grp
    FROM growth_flags
),
streaks AS (
    SELECT
        company_id,
        grp,
        COUNT(*) AS consecutive_years
    FROM streak_groups
    WHERE grew = 1
    GROUP BY company_id, grp
)
SELECT DISTINCT
    s.company_id,
    c.ticker,
    c.company_name,
    s.consecutive_years
FROM streaks s
JOIN companies c ON s.company_id = c.company_id
WHERE s.consecutive_years >= 5
ORDER BY s.consecutive_years DESC, c.ticker;

-- ── Query 10: Peer group comparison — count per group + avg ROE from latest year ──
-- Purpose: Summarise peer-group composition and performance.
SELECT
    pp.peer_group,
    COUNT(DISTINCT pp.company_id)                      AS company_count,
    ROUND(AVG(fr.roe), 2)                              AS avg_roe,
    ROUND(AVG(fr.net_profit_margin), 2)                AS avg_npm,
    ROUND(AVG(fr.debt_to_equity), 2)                   AS avg_de
FROM peer_percentiles pp
JOIN financial_ratios fr ON pp.company_id = fr.company_id AND pp.year = fr.year
WHERE pp.year = (SELECT MAX(year) FROM peer_percentiles)
  AND pp.metric_name = 'roe'
GROUP BY pp.peer_group
ORDER BY company_count DESC;
