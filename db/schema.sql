PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    company_name TEXT NOT NULL,
    sector_name TEXT,
    industry TEXT,
    market_cap REAL,
    listing_status TEXT DEFAULT 'Active',
    isin TEXT,
    bse_code TEXT,
    nse_symbol TEXT,
    founded_year INTEGER,
    website TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sectors (
    sector_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS profitandloss (
    pnl_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    sales REAL,
    operating_profit REAL,
    operating_profit_margin REAL,
    net_profit REAL,
    eps REAL,
    dividend_payout_pct REAL,
    tax_rate REAL,
    depreciation REAL,
    interest_expense REAL,
    other_income REAL,
    total_revenue REAL,
    cogs REAL,
    employee_cost REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year)
);

CREATE TABLE IF NOT EXISTS balancesheet (
    bs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    total_assets REAL,
    total_liabilities REAL,
    shareholders_equity REAL,
    total_debt REAL,
    current_assets REAL,
    current_liabilities REAL,
    cash_and_equivalents REAL,
    inventory REAL,
    trade_receivables REAL,
    investments REAL,
    fixed_assets REAL,
    intangible_assets REAL,
    borrowings_current REAL,
    borrowings_noncurrent REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year)
);

CREATE TABLE IF NOT EXISTS cashflow (
    cf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    operating_activities REAL,
    investing_activities REAL,
    financing_activities REAL,
    net_cash_flow REAL,
    capex REAL,
    fcf REAL,
    dividends_paid REAL,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year)
);

CREATE TABLE IF NOT EXISTS stock_prices (
    sp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, trade_date)
);

CREATE TABLE IF NOT EXISTS analysis (
    analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER,
    analysis_type TEXT,
    metric_name TEXT,
    metric_value REAL,
    description TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year, analysis_type, metric_name)
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    doc_type TEXT,
    doc_name TEXT,
    file_path TEXT,
    uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, doc_type, doc_name)
);

CREATE TABLE IF NOT EXISTS financial_ratios (
    fr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    net_profit_margin REAL,
    operating_profit_margin REAL,
    gross_profit_margin REAL,
    roe REAL,
    roce REAL,
    roa REAL,
    roic REAL,
    debt_to_equity REAL,
    interest_coverage REAL,
    net_debt REAL,
    net_debt_to_ebitda REAL,
    asset_turnover REAL,
    current_ratio REAL,
    quick_ratio REAL,
    inventory_turnover REAL,
    dividend_yield REAL,
    fcf_yield REAL,
    ev_to_ebitda REAL,
    pe_ratio REAL,
    pb_ratio REAL,
    cfo_quality REAL,
    capex_intensity TEXT,
    allocation_pattern TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year)
);

CREATE TABLE IF NOT EXISTS peer_percentiles (
    pp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    percentile_rank REAL,
    peer_group TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id),
    UNIQUE(company_id, year, metric_name, peer_group)
);

CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_sector_name ON companies(sector_name);
CREATE INDEX IF NOT EXISTS idx_companies_listing_status ON companies(listing_status);
CREATE INDEX IF NOT EXISTS idx_companies_market_cap ON companies(market_cap);

CREATE INDEX IF NOT EXISTS idx_profitandloss_company_id ON profitandloss(company_id);
CREATE INDEX IF NOT EXISTS idx_profitandloss_year ON profitandloss(year);
CREATE INDEX IF NOT EXISTS idx_profitandloss_company_year ON profitandloss(company_id, year);

CREATE INDEX IF NOT EXISTS idx_balancesheet_company_id ON balancesheet(company_id);
CREATE INDEX IF NOT EXISTS idx_balancesheet_year ON balancesheet(year);
CREATE INDEX IF NOT EXISTS idx_balancesheet_company_year ON balancesheet(company_id, year);

CREATE INDEX IF NOT EXISTS idx_cashflow_company_id ON cashflow(company_id);
CREATE INDEX IF NOT EXISTS idx_cashflow_year ON cashflow(year);
CREATE INDEX IF NOT EXISTS idx_cashflow_company_year ON cashflow(company_id, year);

CREATE INDEX IF NOT EXISTS idx_stock_prices_company_id ON stock_prices(company_id);
CREATE INDEX IF NOT EXISTS idx_stock_prices_trade_date ON stock_prices(trade_date);
CREATE INDEX IF NOT EXISTS idx_stock_prices_company_date ON stock_prices(company_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_analysis_company_id ON analysis(company_id);
CREATE INDEX IF NOT EXISTS idx_analysis_year ON analysis(year);
CREATE INDEX IF NOT EXISTS idx_analysis_type ON analysis(analysis_type);

CREATE INDEX IF NOT EXISTS idx_documents_company_id ON documents(company_id);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);

CREATE INDEX IF NOT EXISTS idx_financial_ratios_company_id ON financial_ratios(company_id);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_year ON financial_ratios(year);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_company_year ON financial_ratios(company_id, year);

CREATE INDEX IF NOT EXISTS idx_peer_percentiles_company_id ON peer_percentiles(company_id);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_year ON peer_percentiles(year);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_metric_name ON peer_percentiles(metric_name);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_peer_group ON peer_percentiles(peer_group);
