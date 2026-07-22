# Nifty 100 Financial Analytics Engine

A complete toolkit for analysing India's top 100 listed companies — from raw data ingestion all the way to interactive dashboards and radar charts. Think of it as your personal research assistant that does the number-crunching so you can focus on what the numbers actually mean.

---

## ✨ What is this?

You feed it raw financial statements (P&L, balance sheet, cash flow) in CSV or Excel format. It validates the data against **16 quality checks**, computes **21 financial ratios**, runs every company through **6 curated investment presets**, compares them against their **peer groups**, and serves everything through a **REST API**. It even draws radar charts so you can visually compare a company against its sector.

Built in 3 sprints, end-to-end. No shortcuts, no half-baked modules.

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create your .env file
cp .env.example .env       # or just create one with DB_PATH=db/nifty100.db

# 3. Drop your CSV/Excel files into data/

# 4. Run the ETL pipeline (ingest + validate)
make load

# 5. Compute financial ratios
make ratios
```

That's it. You now have a fully populated SQLite database with validated data and computed ratios. Want to screen companies against a preset?

```bash
make report    # exports screener_output.xlsx with color-coded results
make radar     # generates radar charts for every company
make api       # starts the FastAPI server at http://localhost:8000
```

---

## 🧱 What's Inside

### Sprint 1 — Data Foundation (ETL)

The boring-but-critical stuff. Raw data comes in messy — tickers with whitespace, years embedded in strings like "FY2020-21", Indian number formats like `1,23,45,678`, percentages mixed with raw numbers. This layer cleans it all up.

| Component | What it does |
|-----------|-------------|
| **10-table SQLite schema** | Companies, P&L, Balance Sheet, Cash Flow, Stock Prices, Financial Ratios, Peer Percentiles, Sectors, Analysis, Documents — all with foreign keys and composite unique constraints |
| **Normaliser** | Handles tickers, years (extracts from strings), numeric values (commas, percentages, dashes), and sector name standardisation (18 sector mappings) |
| **Validator** | 16 data quality rules — from basic stuff like duplicate keys to balance-sheet equation checks (Assets = Liabilities + Equity within 1%) and OPM cross-verification |
| **Loader** | Auto-detects file types by column names, maps them to tables, normalises and loads in dependency order. Exports `load_audit.csv` and `validation_failures.csv` |

**16 DQ Rules:** PK uniqueness · Composite PK · FK integrity · BS balance (<1%) · OPM cross-check · Positive sales · Negative cash · Tax rate bounds · Dividend cap · Valid URLs · EPS/profit sign match · CA/CL ratio · Table coverage · Year range · Duplicate tickers · Positive market cap

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

**104 tests, 0 failures,** runs in ~2 seconds:

| Module | Tests | What's covered |
|--------|-------|---------------|
| `test_normaliser.py` | 49 | Ticker (8), year (11), numeric (10), sector (3), DQ rules (16) + export |
| `test_ratios.py` | 40 | NPM, OPM, ROE, ROCE, ROA, D/E, ICR, CAGR (6 edge cases), RatioEngine, CashFlow (11) |
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
│   └── schema.sql                  # 10 tables, all constraints + indexes
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
│   └── api.py                     # FastAPI with 5 endpoints
├── tests/
│   ├── etl/test_normaliser.py     # 49 tests
│   └── kpi/
│       ├── test_ratios.py         # 40 tests
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
| `make report` | Run screener → Excel workbook |
| `make test` | Run all 104 tests |
| `make api` | Start FastAPI with hot reload |
| `make dashboard` | Start API via `python -m src.api` |
| `make clean` | Wipe database, outputs, and caches |

---

## 🔒 License & Credit

Built as a complete end-to-end financial analytics system. All data processing happens locally — nothing leaves your machine unless you deploy the API.
