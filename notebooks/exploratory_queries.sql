-- ═══════════════════════════════════════════════════════════════
-- Nifty 100 Financial Analytics — Exploratory SQL Queries
-- Database: db/nifty100.db (SQLite)
-- Schema: 12 tables (companies, sectors, profitandloss, balancesheet,
--          cashflow, analysis, documents, prosandcons, stock_prices,
--          financial_ratios, peer_groups, market_cap)
-- ═══════════════════════════════════════════════════════════════

-- ── Query 1: Row counts for all 12 tables ──────────────────────
-- Purpose: Quick data-volume survey to confirm data loaded correctly.
SELECT 'companies'        AS table_name, COUNT(*) AS row_count FROM companies
UNION ALL SELECT 'sectors',          COUNT(*) FROM sectors
UNION ALL SELECT 'profitandloss',    COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet',     COUNT(*) FROM balancesheet
UNION ALL SELECT 'cashflow',         COUNT(*) FROM cashflow
UNION ALL SELECT 'analysis',         COUNT(*) FROM analysis
UNION ALL SELECT 'documents',        COUNT(*) FROM documents
UNION ALL SELECT 'prosandcons',      COUNT(*) FROM prosandcons
UNION ALL SELECT 'stock_prices',     COUNT(*) FROM stock_prices
UNION ALL SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL SELECT 'peer_groups',      COUNT(*) FROM peer_groups
UNION ALL SELECT 'market_cap',       COUNT(*) FROM market_cap
ORDER BY table_name;

-- ── Query 2: Sector distribution (companies per broad_sector) ──
-- Purpose: Understand how many companies fall into each sector bucket.
SELECT
    broad_sector,
    COUNT(*) AS company_count
FROM companies
WHERE broad_sector IS NOT NULL
GROUP BY broad_sector
ORDER BY company_count DESC;

-- ── Query 3: Year coverage (min / max year per year-bearing table) ──
-- Purpose: Verify temporal coverage across fact tables.
SELECT 'profitandloss'    AS table_name, MIN(year) AS min_year, MAX(year) AS max_year FROM profitandloss
UNION ALL SELECT 'balancesheet',     MIN(year), MAX(year) FROM balancesheet
UNION ALL SELECT 'cashflow',         MIN(year), MAX(year) FROM cashflow
UNION ALL SELECT 'financial_ratios', MIN(year), MAX(year) FROM financial_ratios
UNION ALL SELECT 'market_cap',       MIN(year), MAX(year) FROM market_cap
UNION ALL SELECT 'documents',        MIN(year), MAX(year) FROM documents
ORDER BY table_name;

-- ── Query 4: FK integrity — P&L rows without a matching company ──
-- Purpose: Catch orphan rows before they skew analytics.
SELECT DISTINCT p.company_id
FROM profitandloss p
LEFT JOIN companies c ON p.company_id = c.company_id
WHERE c.company_id IS NULL
ORDER BY p.company_id;

-- ── Query 5: Top 10 companies by market cap ──
-- Purpose: Identify the index heavyweights.
SELECT company_id, ticker, company_name, market_cap_crore
FROM companies
WHERE market_cap_crore IS NOT NULL
ORDER BY market_cap_crore DESC
LIMIT 10;

-- ── Query 6: Average OPM by sector (most recent year, anomalies excluded) ──
-- Purpose: Compare sector-wise operating profitability.
SELECT
    c.broad_sector,
    ROUND(AVG(p.opm_percentage), 2) AS avg_opm_pct,
    COUNT(DISTINCT p.company_id)     AS company_count
FROM profitandloss p
JOIN companies c ON p.company_id = c.company_id
WHERE p.year = (SELECT MAX(year) FROM profitandloss)
  AND p.opm_percentage IS NOT NULL
  AND p.opm_percentage BETWEEN -100 AND 100
GROUP BY c.broad_sector
ORDER BY avg_opm_pct DESC;

-- ── Query 7: Companies with no stock price data ──
-- Purpose: Identify companies missing in the stock_prices table.
SELECT c.company_id, c.ticker, c.company_name
FROM companies c
LEFT JOIN stock_prices sp ON c.company_id = sp.company_id
WHERE sp.sp_id IS NULL
ORDER BY c.ticker;

-- ── Query 8: Aggregate trends by year (avg net profit, revenue, ROE) ──
-- Purpose: Spot macro-level trends across the Nifty 100 universe.
SELECT
    p.year,
    ROUND(AVG(p.net_profit), 2)   AS avg_net_profit,
    ROUND(AVG(p.sales), 2)        AS avg_revenue,
    ROUND(AVG(fr.return_on_equity_pct), 2) AS avg_roe,
    COUNT(DISTINCT p.company_id)  AS companies_reported
FROM profitandloss p
LEFT JOIN financial_ratios fr ON p.company_id = fr.company_id AND p.year = fr.year
WHERE p.net_profit IS NOT NULL
GROUP BY p.year
ORDER BY p.year;

-- ── Query 9: Companies with 5+ consecutive years of revenue growth ──
-- Purpose: Identify compounding-growth stories.
WITH ordered AS (
    SELECT
        company_id, year, sales,
        LAG(sales) OVER (PARTITION BY company_id ORDER BY year) AS prev_sales
    FROM profitandloss
    WHERE sales IS NOT NULL
),
growth_flags AS (
    SELECT company_id, year, sales, prev_sales,
           CASE WHEN sales > prev_sales THEN 1 ELSE 0 END AS grew
    FROM ordered WHERE prev_sales IS NOT NULL
),
streak_groups AS (
    SELECT company_id, year, grew,
           year - ROW_NUMBER() OVER (PARTITION BY company_id, grew ORDER BY year) AS grp
    FROM growth_flags
),
streaks AS (
    SELECT company_id, grp, COUNT(*) AS consecutive_years
    FROM streak_groups WHERE grew = 1
    GROUP BY company_id, grp
)
SELECT DISTINCT s.company_id, c.ticker, c.company_name, s.consecutive_years
FROM streaks s
JOIN companies c ON s.company_id = c.company_id
WHERE s.consecutive_years >= 5
ORDER BY s.consecutive_years DESC, c.ticker;

-- ── Query 10: Peer group composition + average ROE (latest year) ──
-- Purpose: Summarise peer-group membership and performance.
SELECT
    pg.peer_group_name,
    COUNT(DISTINCT pg.company_id)                AS company_count,
    ROUND(AVG(fr.return_on_equity_pct), 2)       AS avg_roe,
    ROUND(AVG(fr.net_profit_margin_pct), 2)      AS avg_npm,
    ROUND(AVG(fr.debt_to_equity), 2)             AS avg_de
FROM peer_groups pg
JOIN financial_ratios fr ON pg.company_id = fr.company_id
WHERE fr.year = (SELECT MAX(year) FROM financial_ratios)
GROUP BY pg.peer_group_name
ORDER BY company_count DESC;
