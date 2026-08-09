PRAGMA foreign_keys = ON;

-- ═══════════════════════════════════════════════════════════════
-- Nifty 100 Financial Analytics — SQLite schema (spec-aligned)
-- 12 tables: one per source file (7 core + 5 supplementary).
-- ═══════════════════════════════════════════════════════════════

-- ── companies.xlsx + sectors.xlsx + market_cap.xlsx ─────────────
CREATE TABLE IF NOT EXISTS companies (
    company_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT UNIQUE NOT NULL,
    company_name        TEXT,
    about_company       TEXT,
    website             TEXT,
    nse_symbol          TEXT,
    bse_code            TEXT,
    face_value          REAL,
    book_value          REAL,
    roe_percentage      REAL,
    roce_percentage     REAL,
    broad_sector        TEXT,
    sub_sector          TEXT,
    index_weight_pct    REAL,
    market_cap_category TEXT,
    market_cap_crore    REAL
);

-- ── sectors.xlsx (distinct sector list) ─────────────────────────
CREATE TABLE IF NOT EXISTS sectors (
    sector_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name  TEXT UNIQUE NOT NULL
);

-- ── profitandloss.xlsx ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profitandloss (
    pnl_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id        INTEGER NOT NULL,
    year              INTEGER NOT NULL,
    sales             REAL,
    expenses          REAL,
    operating_profit  REAL,
    opm_percentage    REAL,
    other_income      REAL,
    interest          REAL,
    depreciation      REAL,
    profit_before_tax REAL,
    tax_percentage    REAL,
    net_profit        REAL,
    eps               REAL,
    dividend_payout   REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year)
);

-- ── balancesheet.xlsx ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balancesheet (
    bs_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id         INTEGER NOT NULL,
    year               INTEGER NOT NULL,
    equity_capital     REAL,
    reserves           REAL,
    borrowings         REAL,
    other_liabilities  REAL,
    total_liabilities  REAL,
    fixed_assets       REAL,
    cwip               REAL,
    investments        REAL,
    other_asset        REAL,
    total_assets       REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year)
);

-- ── cashflow.xlsx ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cashflow (
    cf_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id           INTEGER NOT NULL,
    year                 INTEGER NOT NULL,
    operating_activity   REAL,
    investing_activity   REAL,
    financing_activity   REAL,
    net_cash_flow        REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year)
);

-- ── analysis.xlsx (text fields parsed in Sprint 5) ─────────────
CREATE TABLE IF NOT EXISTS analysis (
    analysis_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                INTEGER NOT NULL,
    compounded_sales_growth   TEXT,
    compounded_profit_growth  TEXT,
    stock_price_cagr          TEXT,
    roe                       TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ── documents.xlsx ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    doc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL,
    year          INTEGER,
    annual_report TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ── prosandcons.xlsx ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prosandcons (
    pc_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL,
    pros        TEXT,
    cons        TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ── stock_prices.xlsx ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stock_prices (
    sp_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     INTEGER NOT NULL,
    date           TEXT NOT NULL,
    open_price     REAL,
    high_price     REAL,
    low_price      REAL,
    close_price    REAL,
    volume         INTEGER,
    adjusted_close REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, date)
);

-- ── financial_ratios (computed by the Sprint 2 ratio engine) ─────
CREATE TABLE IF NOT EXISTS financial_ratios (
    fr_id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                     INTEGER NOT NULL,
    year                           INTEGER NOT NULL,
    -- profitability
    net_profit_margin_pct          REAL,
    operating_profit_margin_pct    REAL,
    return_on_equity_pct           REAL,
    return_on_capital_employed_pct REAL,
    return_on_assets_pct           REAL,
    -- leverage
    debt_to_equity                 REAL,
    interest_coverage              REAL,
    icr_label                      TEXT,
    high_leverage_flag             BOOLEAN,
    icr_warning_flag               BOOLEAN,
    net_debt_cr                    REAL,
    -- efficiency
    asset_turnover                 REAL,
    -- cash flow
    free_cash_flow_cr              REAL,
    capex_cr                       REAL,
    fcf_conversion_pct             REAL,
    capex_intensity_pct            REAL,
    cfo_quality_score              REAL,
    cfo_quality_label              TEXT,
    capital_allocation_pattern     TEXT,
    -- per-share / payout (from P&L)
    earnings_per_share             REAL,
    book_value_per_share           REAL,
    dividend_payout_ratio_pct      REAL,
    total_debt_cr                  REAL,
    cash_from_operations_cr        REAL,
    -- growth (CAGR windows)
    revenue_cagr_3yr               REAL,
    revenue_cagr_5yr               REAL,
    revenue_cagr_10yr              REAL,
    pat_cagr_3yr                   REAL,
    pat_cagr_5yr                   REAL,
    pat_cagr_10yr                  REAL,
    eps_cagr_3yr                   REAL,
    eps_cagr_5yr                   REAL,
    eps_cagr_10yr                  REAL,
    revenue_cagr_5yr_flag          TEXT,
    pat_cagr_5yr_flag              TEXT,
    eps_cagr_5yr_flag              TEXT,
    -- composite (computed in Sprint 3)
    composite_quality_score        REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year)
);

-- ── peer_groups.xlsx ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS peer_groups (
    pg_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_group_name  TEXT NOT NULL,
    company_id       INTEGER NOT NULL,
    is_benchmark     BOOLEAN DEFAULT 0,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ── market_cap.xlsx ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_cap (
    mc_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id            INTEGER NOT NULL,
    year                  INTEGER NOT NULL,
    market_cap_crore      REAL,
    enterprise_value_crore REAL,
    pe_ratio              REAL,
    pb_ratio              REAL,
    ev_ebitda             REAL,
    dividend_yield_pct    REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year)
);

-- ── peer_percentiles (Sprint 3 — percentile rank per peer group) ──
CREATE TABLE IF NOT EXISTS peer_percentiles (
    pp_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL,
    percentile_rank REAL,
    peer_group      TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE (company_id, year, metric, peer_group)
);

-- ═══════════════════════════════════════════════════════════════
-- Indexes on join/query columns.
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_companies_ticker        ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_broad_sector  ON companies(broad_sector);

CREATE INDEX IF NOT EXISTS idx_pl_company_year ON profitandloss(company_id, year);
CREATE INDEX IF NOT EXISTS idx_bs_company_year ON balancesheet(company_id, year);
CREATE INDEX IF NOT EXISTS idx_cf_company_year ON cashflow(company_id, year);

CREATE INDEX IF NOT EXISTS idx_sp_company_date  ON stock_prices(company_id, date);
CREATE INDEX IF NOT EXISTS idx_fr_company_year  ON financial_ratios(company_id, year);
CREATE INDEX IF NOT EXISTS idx_mc_company_year  ON market_cap(company_id, year);
CREATE INDEX IF NOT EXISTS idx_pp_group_metric  ON peer_percentiles(peer_group, metric);

CREATE INDEX IF NOT EXISTS idx_documents_company_id ON documents(company_id);
CREATE INDEX IF NOT EXISTS idx_analysis_company_id  ON analysis(company_id);
CREATE INDEX IF NOT EXISTS idx_prosandcons_company_id ON prosandcons(company_id);
CREATE INDEX IF NOT EXISTS idx_peer_groups_group     ON peer_groups(peer_group_name);
