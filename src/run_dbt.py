"""Run dbt with settings from .env (dbt itself does not read .env files).

Usage:
    python -m src.run_dbt                    # dbt build on the local lake
    python -m src.run_dbt --target cloud     # dbt build reading raw files from S3
    python -m src.run_dbt --command test     # any dbt command
    python -m src.run_dbt --stage forecast   # the forecast models, after `python -m src.forecast`
    python -m src.run_dbt --full-refresh     # rebuild incremental models from scratch
"""
from __future__ import annotations

import argparse
import json
import os

from dbt.cli.main import dbtRunner

from src.ingestion import config  # loads .env into the environment

TRANSFORM_DIR = config.PROJECT_ROOT / "transform"


# The forecast models read predictions that src/forecast writes AFTER the main build, so they run as a
# second stage:  run_dbt (main)  ->  python -m src.forecast  ->  run_dbt --stage forecast
STAGES = {"main": ["--exclude", "tag:forecast"], "forecast": ["--select", "tag:forecast"], "all": []}


def run(command: str = "build", target: str = "dev", stage: str = "main", full_refresh: bool = False) -> bool:
    args = [*command.split(), "--profiles-dir", ".", "--target", target, *STAGES[stage]]
    if full_refresh:  # rebuild incremental models from scratch (needed after changing their logic or columns)
        args.append("--full-refresh")
    # Warehouse file and raw lake follow DATA_DIR, so the demo can build in its own folder.
    os.environ.setdefault("DBT_DUCKDB_PATH", str(config.DATA_DIR / "warehouse.duckdb"))
    if target == "cloud":
        if not config.S3_BUCKET:
            raise SystemExit("S3_BUCKET is not set. Add it to your .env file.")
        args += ["--vars", json.dumps({"raw_dir": f"s3://{config.S3_BUCKET}/raw"})]
    else:
        args += ["--vars", json.dumps({"raw_dir": config.RAW_DIR.as_posix()})]
    cwd = os.getcwd()
    os.chdir(TRANSFORM_DIR)  # profile and var paths are relative to transform/
    try:
        result = dbtRunner().invoke(args)
    finally:
        os.chdir(cwd)
    return result.success


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["dev", "cloud"], default="dev")
    ap.add_argument("--command", default="build")
    ap.add_argument("--stage", choices=list(STAGES), default="main",
                    help="main: everything except the forecast models; forecast: only them")
    ap.add_argument("--full-refresh", action="store_true",
                    help="rebuild incremental models from scratch instead of processing only recent hours")
    a = ap.parse_args()
    raise SystemExit(0 if run(a.command, a.target, a.stage, a.full_refresh) else 1)


if __name__ == "__main__":
    main()
