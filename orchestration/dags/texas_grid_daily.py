"""Daily Texas grid + weather pipeline.

    ingest_grid ───┐
    ingest_zones ──┤                                                            ┌─► report
                  ├─► upload_to_s3 (skipped if S3 not configured) ─► dbt_build ─┤
    ingest_weather┘                                                            └─► export_dashboard

Each task shells out to the same CLI commands you run by hand, so the
pipeline behaves identically in Airflow and in a terminal.
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# Project root (this file lives in <root>/orchestration/dags/).
PROJECT_DIR = str(Path(__file__).resolve().parents[2])
# Pipeline code runs in its own virtualenv so dbt's dependencies never clash with Airflow's.
PY = os.getenv("PIPELINE_PYTHON", sys.executable)
DBT_TARGET = os.getenv("DBT_TARGET", "dev")

DEFAULT_ARGS = {
    "owner": "ram",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="texas_grid_daily",
    description="Daily incremental load: EIA grid + weather -> S3 -> dbt -> report",
    schedule="0 7 * * *",  # 7:00 AM Central, after EIA publishes the previous day
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Chicago"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["texas-grid", "daily"],
) as daily:
    ingest_grid = BashOperator(
        task_id="ingest_grid",
        bash_command=f"{PY} -m src.ingestion.eia_demand --days 7",
        cwd=PROJECT_DIR,
    )

    ingest_zones = BashOperator(
        task_id="ingest_zones",
        bash_command=f"{PY} -m src.ingestion.eia_zones --days 7",
        cwd=PROJECT_DIR,
    )

    ingest_weather = BashOperator(
        task_id="ingest_weather",
        bash_command=f"{PY} -m src.ingestion.weather --days 14",
        cwd=PROJECT_DIR,
    )

    # Exit code 99 marks the task "skipped" (not failed) when S3 isn't set up yet.
    upload_to_s3 = BashOperator(
        task_id="upload_to_s3",
        bash_command=(
            'if [ -z "${S3_BUCKET:-}" ]; then echo "S3_BUCKET not set - skipping upload"; exit 99; fi; '
            f"{PY} -m src.storage.s3_sync"
        ),
        cwd=PROJECT_DIR,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{PY} -m src.run_dbt --target {DBT_TARGET}",
        cwd=PROJECT_DIR,
        trigger_rule="none_failed",  # run even when the S3 upload was skipped
    )

    report = BashOperator(
        task_id="report",
        bash_command=f"{PY} -m src.report",
        cwd=PROJECT_DIR,
    )

    export_dashboard = BashOperator(
        task_id="export_dashboard",
        bash_command=f"{PY} -m src.export_dashboard",
        cwd=PROJECT_DIR,
    )

    [ingest_grid, ingest_zones, ingest_weather] >> upload_to_s3 >> dbt_build >> [report, export_dashboard]


with DAG(
    dag_id="texas_grid_backfill",
    description="Manual backfill from a start date (safe to re-run: skips months already loaded)",
    schedule=None,
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Chicago"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"start": "2021-01-01"},
    tags=["texas-grid", "backfill"],
) as backfill:
    grid = BashOperator(
        task_id="backfill_grid",
        bash_command=f"{PY} -m src.ingestion.eia_demand --start {{{{ params.start }}}}",
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(hours=3),
    )
    zones = BashOperator(
        task_id="backfill_zones",
        bash_command=f"{PY} -m src.ingestion.eia_zones --start {{{{ params.start }}}}",
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(hours=3),
    )
    weather = BashOperator(
        task_id="backfill_weather",
        bash_command=f"{PY} -m src.ingestion.weather --start {{{{ params.start }}}}",
        cwd=PROJECT_DIR,
    )
    sync = BashOperator(
        task_id="upload_to_s3",
        bash_command=(
            'if [ -z "${S3_BUCKET:-}" ]; then echo "S3_BUCKET not set - skipping upload"; exit 99; fi; '
            f"{PY} -m src.storage.s3_sync"
        ),
        cwd=PROJECT_DIR,
    )
    build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{PY} -m src.run_dbt --target {DBT_TARGET}",
        cwd=PROJECT_DIR,
        trigger_rule="none_failed",
    )
    [grid, zones, weather] >> sync >> build
