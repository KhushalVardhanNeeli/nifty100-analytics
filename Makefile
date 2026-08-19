.PHONY: all load ratios cagr screener peer radar export api dashboard test clean verify

all: load ratios cagr screener peer radar export

# ── Sprint 1: Data Foundation ────────────────────────────────────
load:
	python -m src.etl.loader

# ── Sprint 2: Ratio Engine ──────────────────────────────────────
ratios:
	python -m src.analytics.ratios

cagr:
	python -m src.analytics.cagr

export:
	python -m src.analytics.exports

# ── Sprint 3: Screener & Peer ────────────────────────────────────
screener:
	python -c "from src.screener.engine import ScreenerEngine; ScreenerEngine().run_all()"

peer:
	python -c "from src.analytics.peer import PeerAnalyzer; p=PeerAnalyzer(); p.compute_percentiles(); p.export()"

radar:
	python -m src.analytics.radar

# ── Sprint 4: Dashboard & Valuation ──────────────────────────────
dashboard:
	streamlit run src/dashboard/app.py --server.port 8501

valuation:
	python -m src.analytics.valuation

# ── Sprint 5: NLP & Reports ─────────────────────────────────────
reports:
	python -m src.reports.tearsheet
	python -m src.reports.sector_report
	python -m src.reports.portfolio

nlp:
	python -m src.nlp.parser
	python -m src.nlp.pros_cons_generator

intelligence:
	python -m src.analytics.cashflow_kpis

# ── Sprint 6: API, ML, Tests ─────────────────────────────────────
api:
	uvicorn src.api:app --reload --host 0.0.0.0 --port 8000

ml:
	python -m src.ml.clustering

test:
	python -m pytest tests/ -v --tb=short -ra

test-cov:
	python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term

# ── Utilities ────────────────────────────────────────────────────
verify:
	python -c "\
import sqlite3; \
conn = sqlite3.connect('db/nifty100.db'); \
tables = ['companies','profitandloss','balancesheet','cashflow','stock_prices', \
    'financial_ratios','peer_percentiles','sectors','analysis','documents']; \
for t in tables: \
    try: \
        c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]; \
        print(f'{t}: {c} rows'); \
    except Exception as e: \
        print(f'{t}: ERROR - {e}'); \
conn.close(); \
print(); \
import os; \
tearsheets = len([f for f in os.listdir('output/') if f.endswith('.pdf')]); \
print(f'Tearsheet PDFs: {tearsheets}'); \
radars = len([f for f in os.listdir('reports/radar_charts/') if f.endswith('.png')]) if os.path.exists('reports/radar_charts/') else 0; \
print(f'Radar charts: {radars}')"

clean:
	rm -f db/nifty100.db
	rm -rf output/*
	rm -rf reports/radar_charts/*
	rm -rf reports/sector_pdfs/*
	rm -rf reports/tearsheets/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

reset: clean load ratios cagr screener peer radar export
