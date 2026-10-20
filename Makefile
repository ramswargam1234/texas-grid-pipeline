# Shortcuts for common tasks. Run `make help` for the list.
# Works on macOS and Linux (Windows: use the python commands shown in the README).

PY ?= .venv/bin/python

.PHONY: help setup demo demo-dashboard test build forecast freshness report dashboard backfill refresh sync

help:  ## Show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

.venv/bin/python:
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt -r dashboard/requirements.txt

setup: .venv/bin/python  ## Create .venv and install dependencies

demo: setup  ## Run the whole pipeline on synthetic data (no API keys, no AWS)
	$(PY) -m src.demo

demo-dashboard: setup  ## Run the demo, then open the dashboard on demo data
	$(PY) -m src.demo --dashboard

test: setup  ## Unit tests
	$(PY) -m pytest -q

build: setup  ## dbt build on your local lake, then the forecast and its models (all tests)
	$(PY) -m src.run_dbt
	$(PY) -m src.forecast
	$(PY) -m src.run_dbt --stage forecast

forecast: setup  ## Re-run the whole demand-forecast backtest, then its dbt models
	$(PY) -m src.forecast --force
	$(PY) -m src.run_dbt --stage forecast

freshness: setup  ## Is every source still delivering? (age of the newest hour per source)
	$(PY) -m src.freshness check

report: setup  ## Print headline findings from the warehouse
	$(PY) -m src.report

dashboard: setup  ## Open the dashboard (committed snapshot of real data)
	$(PY) -m streamlit run dashboard/app.py

backfill: setup  ## Load all real data from 2021 (needs EIA_API_KEY in .env)
	$(PY) -m src.ingestion.eia_demand --start 2021-01-01
	$(PY) -m src.ingestion.eia_zones --start 2021-01-01
	$(PY) -m src.ingestion.eia_fuel --start 2021-01-01
	$(PY) -m src.ingestion.weather --start 2021-01-01
	$(PY) -m src.ingestion.weather_forecast --start 2021-04-01

refresh: setup  ## Load the latest days of real data (needs EIA_API_KEY)
	$(PY) -m src.ingestion.eia_demand --days 7
	$(PY) -m src.ingestion.eia_zones --days 7
	$(PY) -m src.ingestion.eia_fuel --days 7
	$(PY) -m src.ingestion.weather --days 14
	$(PY) -m src.ingestion.weather_forecast --days 10

sync: setup  ## Upload new and changed lake files to S3 (needs AWS keys)
	$(PY) -m src.storage.s3_sync
