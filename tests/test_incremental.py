"""Incremental dbt runs must produce exactly the same tables as a full rebuild.

Scenario: build with data through July, then August arrives AND EIA revises late-July demand. An incremental
run must pick up both. It is compared row by row with a from-scratch build of the same lake.
Takes ~40 s, so it runs in CI (RUN_SLOW_TESTS=1) and is skipped locally by default.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
INCREMENTAL = ["stg_eia__ercot_hourly", "stg_weather__hourly", "stg_eia__ercot_zone_hourly",
               "stg_eia__ercot_fuel_hourly", "fct_grid_hourly", "fct_zone_hourly", "fct_fuel_hourly"]

pytestmark = pytest.mark.skipif(os.getenv("RUN_SLOW_TESTS") != "1", reason="slow: set RUN_SLOW_TESTS=1")


def run(base: Path, *args):
    env = {**os.environ, "DATA_DIR": str(base), "DBT_DUCKDB_PATH": str(base / "warehouse.duckdb"), "DO_NOT_TRACK": "1"}
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def revise_late_july(base: Path):
    f = base / "raw" / "eia_ercot_hourly" / "year=2021" / "month=07" / "data.parquet"
    df = pd.read_parquet(f)
    late = (df["period_utc"] >= pd.Timestamp("2021-07-25", tz="UTC")) & (df["type"] == "D")
    df.loc[late, "value_mwh"] += 500
    df.to_parquet(f, index=False)


def test_incremental_matches_full_refresh(tmp_path):
    full, inc = tmp_path / "full", tmp_path / "inc"
    run(full, "-m", "src.sample_data")
    shutil.copytree(full / "raw", inc / "raw")
    held = tmp_path / "held"
    for p in (inc / "raw").glob("*/year=2021/month=08"):            # August hasn't arrived yet
        shutil.move(str(p), str(held / p.parent.parent.name / "month=08"))
    run(inc, "-m", "src.run_dbt")                                      # first build: full
    for p in held.glob("*/month=08"):                                  # August arrives...
        shutil.move(str(p), str(inc / "raw" / p.parent.name / "year=2021" / "month=08"))
    revise_late_july(inc)                                              # ...and EIA revises late July
    revise_late_july(full)
    run(inc, "-m", "src.run_dbt")                                      # incremental
    run(full, "-m", "src.run_dbt")                                     # from scratch

    con = duckdb.connect()
    con.sql(f"attach '{inc / 'warehouse.duckdb'}' as inc_db (read_only)")
    con.sql(f"attach '{full / 'warehouse.duckdb'}' as full_db (read_only)")
    for t in INCREMENTAL:
        cols = ", ".join(c for c in con.sql(f"select * from full_db.{t} limit 0").columns if c != "ingested_at")
        diff = con.sql(f"""select count(*) from (
            (select {cols} from inc_db.{t} except all select {cols} from full_db.{t})
            union all
            (select {cols} from full_db.{t} except all select {cols} from inc_db.{t}))""").fetchone()[0]
        assert diff == 0, f"{t}: {diff} rows differ between incremental and full refresh"
