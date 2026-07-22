.PHONY: load ratios test report dashboard api clean export radar all

all: load ratios

load:
	python -m src.etl.loader

ratios:
	python -m src.analytics.ratios

export:
	python -m src.analytics.exports

radar:
	python -m src.analytics.radar

report:
	python -m src.screener.engine

test:
	python -m pytest tests/ -v

dashboard:
	python -m src.api

api:
	uvicorn src.api:app --reload --host 0.0.0.0 --port 8000

clean:
	rm -f db/nifty100.db
	rm -rf output/*
	rm -rf reports/radar_charts/*
	rm -rf __pycache__ src/__pycache__ src/etl/__pycache__ src/analytics/__pycache__ src/screener/__pycache__ tests/__pycache__ tests/etl/__pycache__ tests/kpi/__pycache__
