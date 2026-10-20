"""Sync the local Parquet lake (data/raw) with S3.

Only uploads files that are new or changed (compares MD5 with the S3 ETag),
so re-running is cheap and safe.

Writes: s3://<S3_BUCKET>/raw/<dataset>/year=YYYY/month=MM/data.parquet

Usage:
    python -m src.storage.s3_sync              # upload new/changed files
    python -m src.storage.s3_sync --dry-run    # show what would be uploaded
    python -m src.storage.s3_sync --download   # pull new/changed files from S3 (used by CI)
    python -m src.storage.s3_sync --state-download / --state-upload
        # the dbt warehouse file, so snapshot history survives between cloud runs
"""
from __future__ import annotations

import argparse
import hashlib
import logging
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig

from src.ingestion import config

log = logging.getLogger("s3_sync")
# Single-part uploads keep S3's ETag equal to the file's MD5 (monthly files are well under 5 GB).
SINGLE_PART = TransferConfig(multipart_threshold=5 * 1024**3)


def md5_hex(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_etags(s3, bucket: str, prefix: str) -> dict[str, str]:
    """Map of S3 key -> ETag (quotes stripped) for everything under prefix."""
    etags = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            etags[obj["Key"]] = obj["ETag"].strip('"')
    return etags


def sync(local_dir: Path, bucket: str, prefix: str = "raw", s3=None, dry_run: bool = False) -> dict:
    """Upload new/changed *.parquet files. Returns counts for logging and tests."""
    s3 = s3 or boto3.client("s3", region_name=config.AWS_REGION)
    existing = remote_etags(s3, bucket, prefix + "/")
    uploaded = skipped = 0
    for path in sorted(local_dir.rglob("*.parquet")):
        key = f"{prefix}/{path.relative_to(local_dir).as_posix()}"
        if existing.get(key) == md5_hex(path):
            skipped += 1
            continue
        if dry_run:
            log.info("would upload %s", key)
        else:
            s3.upload_file(str(path), bucket, key,
                           ExtraArgs={"ContentType": "application/vnd.apache.parquet"},
                           Config=SINGLE_PART)
            log.info("uploaded %s", key)
        uploaded += 1
    log.info("Done: %d uploaded, %d unchanged (bucket=%s)", uploaded, skipped, bucket)
    return {"uploaded": uploaded, "skipped": skipped}


def download(local_dir: Path, bucket: str, prefix: str = "raw", s3=None) -> dict:
    """Download S3 objects that are missing locally or differ (by MD5). Returns counts."""
    s3 = s3 or boto3.client("s3", region_name=config.AWS_REGION)
    downloaded = skipped = 0
    for key, etag in sorted(remote_etags(s3, bucket, prefix + "/").items()):
        if not key.endswith(".parquet"):
            continue
        path = local_dir / key[len(prefix) + 1:]
        if path.exists() and md5_hex(path) == etag:
            skipped += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(path))
        downloaded += 1
    log.info("Done: %d downloaded, %d unchanged (bucket=%s)", downloaded, skipped, bucket)
    return {"downloaded": downloaded, "skipped": skipped}


STATE_KEY = "state/warehouse.duckdb"


def download_state(bucket: str, s3=None) -> bool:
    """Fetch the previous warehouse (with snapshot history) from S3. Returns False on the first run."""
    s3 = s3 or boto3.client("s3", region_name=config.AWS_REGION)
    target = config.DATA_DIR / "warehouse.duckdb"
    if not remote_etags(s3, bucket, STATE_KEY):
        log.info("No saved warehouse in s3://%s/%s yet; snapshots start fresh", bucket, STATE_KEY)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, STATE_KEY, str(target))
    log.info("Restored warehouse from s3://%s/%s", bucket, STATE_KEY)
    return True


def upload_state(bucket: str, s3=None) -> None:
    """Save the warehouse to S3 after a successful dbt build."""
    s3 = s3 or boto3.client("s3", region_name=config.AWS_REGION)
    source = config.DATA_DIR / "warehouse.duckdb"
    if not source.exists():
        raise SystemExit(f"{source} not found. Run dbt first.")
    s3.upload_file(str(source), bucket, STATE_KEY, Config=SINGLE_PART)
    log.info("Saved warehouse to s3://%s/%s", bucket, STATE_KEY)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--download", action="store_true", help="pull from S3 instead of pushing")
    ap.add_argument("--state-download", action="store_true", help="restore the dbt warehouse from S3")
    ap.add_argument("--state-upload", action="store_true", help="save the dbt warehouse to S3")
    a = ap.parse_args()
    if not config.S3_BUCKET:
        raise SystemExit("S3_BUCKET is not set. Add it to your .env file.")
    if a.state_download:
        download_state(config.S3_BUCKET)
    elif a.state_upload:
        upload_state(config.S3_BUCKET)
    elif a.download:
        download(config.RAW_DIR, config.S3_BUCKET)
    else:
        sync(config.RAW_DIR, config.S3_BUCKET, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
