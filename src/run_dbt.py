"""Run dbt with settings from .env (dbt itself does not read .env files).

Usage:
    python -m src.run_dbt                    # dbt build on the local lake
    python -m src.run_dbt --target cloud     # dbt build reading raw files from S3
    python -m src.run_dbt --command test     # any dbt command
"""
from __future__ import annotations

import argparse
import json
import os

from dbt.cli.main import dbtRunner

from src.ingestion import config  # loads .env into the environment

TRANSFORM_DIR = config.PROJECT_ROOT / "transform"


def run(command: str = "build", target: str = "dev") -> bool:
    args = [command, "--profiles-dir", ".", "--target", target]
    if target == "cloud":
        if not config.S3_BUCKET:
            raise SystemExit("S3_BUCKET is not set. Add it to your .env file.")
        args += ["--vars", json.dumps({"raw_dir": f"s3://{config.S3_BUCKET}/raw"})]
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
    a = ap.parse_args()
    raise SystemExit(0 if run(a.command, a.target) else 1)


if __name__ == "__main__":
    main()
