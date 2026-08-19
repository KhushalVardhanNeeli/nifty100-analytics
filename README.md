# Nifty 100 Financial Analytics Engine

A complete toolkit for analysing India's top 100 listed companies — from raw data ingestion all the way to interactive dashboards and radar charts. Think of it as your personal research assistant that does the number-crunching so you can focus on what the numbers actually mean.

---

## ✨ What is this?

You feed it raw financial statements (P&L, balance sheet, cash flow) in CSV or Excel format. It validates the data against **16 quality checks**, computes **21 financial ratios**, runs every company through **6 curated investment presets**, compares them against their **peer groups**, and serves everything through a **REST API**. It even draws radar charts so you can visually compare a company against its sector.

Built in 3 sprints, end-to-end. No shortcuts, no half-baked modules.

---

## 🚀 Getting Started — A Walkthrough

### What you'll need on your system

- **Python 3.10 or higher** (3.11+ recommended)
- **git** (to clone the repo)
- About **200 MB of free space** (the SQLite database grows as you add years of data)
- That's it. No Postgres, no Docker, no cloud account. Everything runs locally.

### Step 1: Clone and set up

```bash
# Grab the code
git clone https://github.com/KhushalVardhanNeeli/nifty100-analytics.git
cd nifty100-analytics

# (Recommended) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install everything in one shot
pip install -r requirements.txt
```

This pulls in ~20 packages — pandas for data wrangling, FastAPI for the web server, matplotlib for charts, SQLAlchemy for the database, pytest for testing. Nothing exotic.

### Step 2: The `.env` file

The project expects a `.env` file with two settings. There's already one in the repo that works out of the box:

```
DB_PATH=db/nifty100.db
DATA_DIR=data/
```

`db/nifty100.db` is where your SQLite database will live. `data/` is where you'll drop your raw files. If you're happy with these defaults, you don't need to change anything.

### Step 3: Get your data ready

This is the one bit you'll need to do yourself. The system expects **CSV, .xlsx, or .xls** files placed in the `data/` folder. Each file should contain financial statements for the Nifty 100 companies.

Here's what the loader looks for and maps automatically:

| File should contain | Look for columns like | Gets loaded into |
|---------------------|----------------------|-------------------|
| Company info | `id` (ticker), `company_name`, `about_company`, `roe_percentage`, `roce_percentage` | `companies` table |
| Sectors | `company_id`, `broad_sector`, `sub_sector`, `index_weight_pct` | `companies` + `sectors` tables |
| Profit & Loss | `year`, `sales`, `expenses`, `operating_profit`, `opm_percentage`, `net_profit`, `eps`, `dividend_payout` | `profitandloss` table |
| Balance Sheet | `year`, `equity_capital`, `reserves`, `borrowings`, `total_liabilities`, `total_assets` | `balancesheet` table |
| Cash Flow | `year`, `operating_activity`, `investing_activity`, `financing_activity`, `net_cash_flow` | `cashflow` table |
| Stock Prices | `date`, `open_price`, `high_price`, `low_price`, `close_price`, `volume` | `stock_prices` table |
| Market Cap | `company_id`, `year`, `market_cap_crore`, `pe_ratio`, `pb_ratio` | `market_cap` table |

Don't worry about exact column naming — the loader normalises everything to lowercase and strips whitespace, so `Net Profit`, `net_profit`, and `NET PROFIT ` all get picked up. Missing columns are simply skipped. Extra columns are ignored.

> **Don't have Nifty 100 data?** You can test the pipeline with any CSV that has the columns above — even just 5-10 companies. The system will work fine. Screener.Trade, Tijori Finance, or Yahoo Finance are good sources if you're looking.

### Step 4: Build the database

```bash
make load
```

This is the big one. It does three things:

1. **Creates the 12-table schema** — companies, sectors, P&L, balance sheet, cash flow, stock prices, financial ratios, peer groups, market cap, analysis, documents, and pros/cons. All tables get proper primary keys, foreign keys (`PRAGMA foreign_keys = ON`), and indexes.
2. **Normalises every row** — tickers get uppercased, years get extracted from strings like `"FY2020-21"`, `"Mar-13"`, `"Dec 2012"` (and `"TTM"` rows are skipped), numbers like `"1,23,45,678"` become floats, percentages are stored in their source units.
3. **Runs 16 data quality checks** — duplicate primary keys, orphan foreign keys, balance sheet equations, OPM cross-checks, tax rate bounds, invalid URLs, and more. Every violation gets logged to `output/validation_failures.csv` with a severity label (CRITICAL or WARNING).

When it finishes, you'll see a summary on screen and two CSV audit files in `output/`:

- `load_audit.csv` — how many rows were loaded vs rejected per table
- `validation_failures.csv` — which rules failed and where

### Sprint 1 — data notes & documented deviations

The source data carries a few quirks that were resolved deliberately during Sprint 1:

- **101 companies** (not 92). The financial-statement files (`profitandloss`, `balancesheet`, `cashflow`) contain **9 companies that are absent from** `companies.xlsx`/`sectors.xlsx`/`market_cap.xlsx` (`AGTL`, `ULTRACEMCO`, `UNIONBANK`, `UNITDSPR`, `VBL`, `VEDL`, `WIPRO`, `ZOMATO`, `ZYDUSLIFE`). These were added to keep `foreign_key_check = 0`. They have no sector/market-cap/peer reference data (those columns are NULL).
- **10 sectors** (not 11). The source `sectors.xlsx` defines 10 `broad_sector` values.
- **12 tables** (not 10). `peer_groups` and `market_cap` are required downstream, so the schema covers all 12 source files.
- **TTM rows excluded.** `profitandloss.xlsx` has 100 "TTM" (trailing-twelve-month) rows with no fiscal year; these are logged as rejected in `load_audit.csv`.
- **OPM cross-check is WARNING-only.** The source `opm_percentage` field is frequently inconsistent with `operating_profit / sales` (a known source-data discrepancy). DQ-05 reports these as WARNINGs rather than blocking CRITICAL failures.

### Step 5: Compute the ratios

```bash
make ratios
```

This reads the cleaned P&L, balance sheet, and cash flow data and computes **21 financial ratios** for every company, for every year. It populates the `financial_ratios` table.

Smart edge cases are handled throughout:
- Zero denominator? Returns `null` instead of crashing.
- Negative equity? ROE and ROCE return `null` (meaningless metric).
- Company has zero debt? D/E returns `0`, not `null` — because being debt-free is good information.
- Financial sector with D/E > 5? Flagged as a warning (banks naturally run high leverage).
- Interest expense of zero and operating profit positive? ICR is labelled "Debt Free" instead of infinite.
- ICR between 0 and 1.5? Warning raised — this company might struggle to service its debt.

### Step 6: Explore the results

Now the fun part. You can:

```bash
# Screen companies against any of the 6 investment presets
make report    # → output/screener_output.xlsx (color-coded Excel)

# Compare companies against their peers
make export    # → output/peer_comparison.xlsx (11 sheets, one per sector)

# Generate radar charts for visual comparison
make radar     # → reports/radar_charts/ (PNG files, 300 DPI)

# Start the API and explore in your browser
make api       # → http://localhost:8000
```

The API gives you:
- `http://localhost:8000/companies` — browse all companies, filter by sector
- `http://localhost:8000/ratios/1` — get all ratios for company ID 1
- `http://localhost:8000/screener/Quality_Compounder` — run a preset and get JSON results
- `http://localhost:8000/dashboard` — summary stats at a glance

### That's the whole flow

```
CSV/Excel files → make load → make ratios → make report / radar / api
   (30 sec)        (10 sec)      (5 sec)         (instant)
```

Under a minute from raw data to interactive dashboard. All local, all yours.

---

## 🧱 What's Inside

### Sprint 1 — Data Foundation (ETL)

The boring-but-critical stuff. Raw data comes in messy — tickers with whitespace, years embedded in strings like "FY2020-21", Indian number formats like `1,23,45,678`, percentages mixed with raw numbers. This layer cleans it all up.

| Component | What it does |
|-----------|-------------|
| **12-table SQLite schema** | Companies, Sectors, P&L, Balance Sheet, Cash Flow, Stock Prices, Financial Ratios, Peer Groups, Market Cap, Analysis, Documents, Pros/Cons — all with foreign keys and composite unique constraints |
| **Normaliser** | Handles tickers, years (extracts from `"Dec 2012"`, `"Mar-13"`, `"FY2020"`, skips `"TTM"`), numeric values (commas, percentages, dashes), and sector name standardisation |
| **Validator** | 16 data quality rules — PK/FK are CRITICAL, everything else is WARNING. Includes balance-sheet equation checks (Assets = Liabilities within 1%) and OPM cross-verification |
| **Loader** | Maps source files to tables, normalises and loads in dependency order. Exports `load_audit.csv` and `validation_failures.csv` |

**16 DQ Rules (PK/FK = CRITICAL, rest = WARNING):** PK uniqueness · Composite PK · FK integrity · BS balance (<1%) · OPM cross-check · Positive sales · Net cash · Tax rate bounds · Dividend cap · Valid URLs · EPS/profit sign match · BS equity reconciliation · Table coverage · Year range · Duplicate tickers · Positive market cap

### Sprint 2 — Financial Ratio Engine

Now the real analysis begins. For every company, for every year, it computes **21 financial ratios** — profitability, efficiency, leverage, valuation, and cash-flow quality.

| Ratio Category | Metrics |
|---------------|---------|
| **Profitability** | Net Profit Margin, Operating Profit Margin, Gross Profit Margin, ROE, ROCE, ROA, ROIC |
| **Leverage** | Debt-to-Equity, Interest Coverage, Net Debt, Net Debt-to-EBITDA |
| **Efficiency** | Asset Turnover, Current Ratio, Quick Ratio, Inventory Turnover |
| **Valuation** | P/E Ratio, P/B Ratio, EV/EBITDA, Dividend Yield, FCF Yield |
| **Cash Flow** | CFO Quality (High/Moderate/Accrual Risk), CapEx Intensity (Asset Light/Moderate/Capital Intensive), FCF Conversion |
| **Growth** | Revenue/PAT/EPS CAGR over 3, 5, and 10-year windows |

**Edge cases handled:** Zero denominators → null · Negative equity → null · Debt-free companies → D/E = 0 (not null) · Financial sector flagged if D/E > 5 · Interest coverage of 0 → labelled "Debt Free" · ICR < 1.5 → warning raised · CAGR with negative start → "Turnaround" flag · Zero base year → "Insufficient" flag

### Sprint 3 — Screener & Peer Engine

This is where it gets practical. You pick an investment philosophy, and the engine finds companies that match.

**6 Presets:**

| Preset | Philosophy |
|--------|-----------|
| **Quality Compounder** | ROE ≥ 15%, revenue CAGR ≥ 10%, CFO quality = High, D/E ≤ 2, NPM ≥ 10% |
| **Value Pick** | P/E ≤ 15, P/B ≤ 2, ROE ≥ 10%, D/E ≤ 1.5, dividend ≥ 2%, ICR ≥ 2 |
| **Growth Accelerator** | Revenue CAGR (5y) ≥ 15%, PAT CAGR (5y) ≥ 12%, ROE ≥ 12%, CapEx Intensive |
| **Dividend Champion** | Dividend ≥ 3%, ROE ≥ 12%, payout ≤ 60%, D/E ≤ 1, ICR ≥ 3 |
| **Debt-Free Blue Chip** | D/E ≤ 0.1, market cap ≥ 10K Cr, ROE ≥ 12%, NPM ≥ 8% |
| **Turnaround Watch** | Revenue CAGR (3y) ≥ -5%, ROE ≥ 5%, ICR ≥ 1, D/E ≤ 3 |

Every result gets a **composite quality score** (0-100) blending profitability, cash quality, growth, and leverage — with winsorisation so outliers don't skew things. Export comes as a color-coded Excel workbook (green ≥ 70, red < 30, yellow in between).

**Peer Analysis:** Companies are grouped into **11 sector-based peer groups**. Within each group, 10 metrics are percentile-ranked. D/E is inverted (lower debt is better, so higher percentile). Outputs an 11-sheet Excel workbook with color-coded cells and median rows per sheet.

**Radar Charts:** 8-axis polar charts comparing each company against its peer group average — saved as 300 DPI PNGs.

---

## 📄 Reports & NLP (Sprint 5)

### Cash Flow Intelligence

```bash
make intelligence        # python -m src.analytics.cashflow_kpis
```

Builds `output/cashflow_intelligence.xlsx` (CFO quality, CapEx intensity,
FCF CAGR, distress & deleveraging flags per company), `output/distress_alerts.csv`,
`output/capital_allocation_distribution.csv` and `output/pattern_changes.csv`
(year-over-year pattern movements).

### NLP — analysis parser & auto pros/cons

```bash
make nlp                # parser + pros/cons generator
```

- `src/nlp/parser.py` — parses `analysis.xlsx` text (e.g. `"10 Years: 21%"`) into
  `output/analysis_parsed.csv`, logs non-matching text to `output/parse_failures.csv`,
  and cross-checks parsed CAGR vs the ratio engine (`output/cagr_crosscheck.csv`).
- `src/nlp/pros_cons_generator.py` — evaluates 12 pro + 12 con rules per company
  (confidence > 60%) into `output/pros_cons_generated.csv` (≥1 pro and ≥1 con per company).

### PDF reports

```bash
make reports            # tearsheets + sector reports + portfolio
```

- `reports/tearsheets/{ticker}_tearsheet.pdf` — 2-page company tearsheet
  (KPIs, revenue/profit bars, ROE/ROCE trend, balance-sheet composition,
  cash-flow waterfall, pros & cons). Skips companies with <3 years of data.
- `reports/sector/{sector}_report.pdf` — per-sector median KPIs + company table.
- `reports/portfolio/portfolio_summary.pdf` — one page per company with trend arrows.

---

## 🖥 Streamlit Dashboard (Sprint 4)

Launch the interactive dashboard:

```bash
make dashboard          # streamlit run src/dashboard/app.py --server.port 8501
# open http://localhost:8501
```

The app uses Streamlit's native multipage layout — use the **sidebar** to navigate the 8 screens:

| Screen | Description |
|--------|-------------|
| **01 Home** | Market-wide KPIs (avg ROE, median P/E, median D/E, debt-free count), sector donut chart, top-5 by composite quality score, year selector |
| **02 Profile** | Company search with autocomplete — company card, 6 KPI tiles, 10-year revenue/profit bars, ROE/ROCE dual-axis chart, pros & cons badges |
| **03 Screener** | 6 preset buttons that auto-fill the sliders, 10 live threshold sliders, result count, CSV download |
| **04 Peers** | Peer-group dropdown, radar chart (company vs group average), KPI table with benchmark row highlighted |
| **05 Trends** | Up to 3 metrics overlaid on 10-year lines with YoY % annotations |
| **06 Sectors** | Sector bubble chart (Revenue vs ROE, size = Market Cap, colour = sub-sector) + median KPI table |
| **07 Capital** | Capital-allocation treemap across the 8 patterns, drill into companies per pattern |
| **08 Reports** | Annual-report PDF links per year with 404 detection (red "Report unavailable" badge) |

All DB queries are cached with `@st.cache_data(ttl=600)` in `src/dashboard/utils/db.py`.

### Valuation module

```bash
make valuation          # python -m src.analytics.valuation
```

Computes FCF yield, 5-year median P/E, sector-median P/E, and Caution/Discount/Fair flags, exporting `output/valuation_summary.xlsx` (92 rows) and `output/valuation_flags.csv`.

---

## 🔌 API Endpoints

Start with `make api` or `uvicorn src.api:app --reload`.

| Endpoint | Description |
|----------|-------------|
| `GET /` | Health check |
| `GET /companies` | List companies (filter by sector, paginate) |
| `GET /ratios/{company_id}` | Get financial ratios for a company (optionally by year) |
| `GET /screener/{preset}` | Run a screener preset and get results as JSON |
| `GET /dashboard` | Summary stats: row counts, sectors, year range, top 5 by market cap |

---

## 🧪 Tests

```bash
make test
```

**125 tests, 0 failures,** runs in ~2 seconds:

| Module | Tests | What's covered |
|--------|-------|---------------|
| `test_normaliser.py` | 66 | Ticker (15), year (21), numeric (10), sector (3), DQ rules (16) + export |
| `test_ratios.py` | 44 | NPM, OPM, ROE, ROCE, ROA, D/E, ICR, net debt, CAGR (6 edge cases), CFO quality, capex intensity, allocation patterns |
| `test_screener_dq.py` | 15 | Validator integration (6), peer metrics (3), screener config (6) |

All tests use mock data — no database required to run.

---

## 📁 Project Structure

```
nifty100-analytics/
├── config/
│   └── screener_config.yaml        # 6 presets with filters and weights
├── data/                            # Drop your CSV/Excel files here
├── db/
│   └── schema.sql                  # 12 tables, all constraints + indexes
├── notebooks/
│   └── exploratory_queries.sql     # 10 ready-to-run SQL queries
├── output/                          # Generated reports land here
│   ├── load_audit.csv
│   ├── validation_failures.csv
│   ├── screener_output.xlsx
│   ├── peer_comparison.xlsx
│   └── capital_allocation.csv
├── reports/
│   └── radar_charts/               # PNG radar charts
├── src/
│   ├── etl/
│   │   ├── normaliser.py           # Data cleaning
│   │   ├── validator.py            # 16 DQ rules
│   │   └── loader.py              # Full ETL orchestrator
│   ├── analytics/
│   │   ├── ratios.py              # 21 financial ratios
│   │   ├── cagr.py                # 3/5/10-year CAGR with edge cases
│   │   ├── cashflow_kpis.py       # CFO quality, capex, allocation patterns
│   │   ├── peer.py                # Peer group percentiles (11 groups)
│   │   ├── exports.py             # Capital allocation + ratio edge-case logs
│   │   └── radar.py              # 8-axis polar radar charts
│   ├── screener/
│   │   └── engine.py             # Composite scoring + Excel export
│   ├── dashboard/
│   │   ├── app.py                # Streamlit entry point
│   │   ├── pages/                # 8 screens (01_home … 08_reports)
│   │   └── utils/db.py           # Cached data loader
│   └── api.py                     # FastAPI with 5 endpoints
├── tests/
│   ├── etl/test_normaliser.py     # 66 tests
│   └── kpi/
│       ├── test_ratios.py         # 44 tests
│       └── test_screener_dq.py    # 15 tests
├── Makefile                        # 10 targets
├── requirements.txt               # 20 Python packages
├── pytest.ini
└── .env
```

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Database | SQLite (via SQLAlchemy) |
| API | FastAPI + Uvicorn |
| Data | pandas, numpy |
| File I/O | openpyxl, xlrd, lxml |
| Charts | matplotlib, seaborn |
| Config | PyYAML, python-dotenv |
| Testing | pytest |

---

## 📋 Makefile Reference

| Command | Action |
|---------|--------|
| `make all` | Full pipeline: load → ratios |
| `make load` | Ingest data + run DQ validation |
| `make ratios` | Compute all financial ratios |
| `make export` | Export capital allocation + edge-case log |
| `make radar` | Generate radar chart PNGs |
| `make nlp` | Parse analysis + generate pros/cons |
| `make reports` | Generate tearsheets, sector + portfolio PDFs |
| `make intelligence` | Cash-flow intelligence exports |
| `make valuation` | Valuation summary + flags |
| `make test` | Run all 125 tests |
| `make api` | Start FastAPI with hot reload |
| `make dashboard` | Launch the Streamlit dashboard on http://localhost:8501 |
| `make clean` | Wipe database, outputs, and caches |

---

## 🔒 License & Credit

Built as a complete end-to-end financial analytics system. All data processing happens locally — nothing leaves your machine unless you deploy the API.
