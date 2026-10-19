"""DAG integrity tests. Skipped automatically where Airflow isn't installed (e.g. the project venv)."""
from pathlib import Path

import pytest

pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402

DAGS_DIR = Path(__file__).resolve().parents[1] / "orchestration" / "dags"


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_daily_dag_structure(dagbag):
    dag = dagbag.dags.get("texas_grid_daily")
    assert dag is not None
    assert set(dag.task_dict) == {"ingest_grid", "ingest_weather", "upload_to_s3", "dbt_build", "report", "export_dashboard"}
    assert dag.task_dict["upload_to_s3"].upstream_task_ids == {"ingest_grid", "ingest_weather"}
    assert dag.task_dict["dbt_build"].trigger_rule == "none_failed"
    assert dag.catchup is False


def test_backfill_dag_is_manual(dagbag):
    dag = dagbag.dags.get("texas_grid_backfill")
    assert dag is not None and dag.schedule is None
    assert dag.params["start"] == "2021-01-01"
