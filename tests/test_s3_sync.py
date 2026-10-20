"""S3 sync tests against moto's in-memory fake S3 (no AWS account needed)."""
import boto3
import pandas as pd
import pytest
from moto import mock_aws

from src.storage.s3_sync import sync

BUCKET = "test-bucket"


@pytest.fixture
def lake(tmp_path):
    for month in ("01", "02"):
        d = tmp_path / "eia_ercot_hourly" / "year=2024" / f"month={month}"
        d.mkdir(parents=True)
        pd.DataFrame({"x": [1, 2, int(month)]}).to_parquet(d / "data.parquet")
    return tmp_path


@pytest.fixture
def s3(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-2")
        client.create_bucket(Bucket=BUCKET,
                             CreateBucketConfiguration={"LocationConstraint": "us-east-2"})
        yield client


def test_uploads_with_partition_layout(lake, s3):
    assert sync(lake, BUCKET, s3=s3) == {"uploaded": 2, "skipped": 0}
    keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"])
    assert keys == ["raw/eia_ercot_hourly/year=2024/month=01/data.parquet",
                    "raw/eia_ercot_hourly/year=2024/month=02/data.parquet"]


def test_second_run_skips_unchanged_and_reuploads_changed(lake, s3):
    sync(lake, BUCKET, s3=s3)
    assert sync(lake, BUCKET, s3=s3) == {"uploaded": 0, "skipped": 2}
    changed = lake / "eia_ercot_hourly" / "year=2024" / "month=02" / "data.parquet"
    pd.DataFrame({"x": [99]}).to_parquet(changed)
    assert sync(lake, BUCKET, s3=s3) == {"uploaded": 1, "skipped": 1}


def test_dry_run_uploads_nothing(lake, s3):
    assert sync(lake, BUCKET, s3=s3, dry_run=True)["uploaded"] == 2
    assert "Contents" not in s3.list_objects_v2(Bucket=BUCKET)


def test_download_pulls_missing_and_changed_files(lake, s3, tmp_path):
    from src.storage.s3_sync import download
    sync(lake, BUCKET, s3=s3)
    target = tmp_path / "fresh"
    assert download(target, BUCKET, s3=s3) == {"downloaded": 2, "skipped": 0}
    assert download(target, BUCKET, s3=s3) == {"downloaded": 0, "skipped": 2}
    got = pd.read_parquet(target / "eia_ercot_hourly" / "year=2024" / "month=01" / "data.parquet")
    assert got["x"].tolist() == [1, 2, 1]


def test_state_round_trip(s3, tmp_path, monkeypatch):
    from src.ingestion import config
    from src.storage.s3_sync import download_state, upload_state
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert download_state(BUCKET, s3=s3) is False  # first run: nothing saved yet
    (tmp_path / "warehouse.duckdb").write_bytes(b"snapshot history")
    upload_state(BUCKET, s3=s3)
    (tmp_path / "warehouse.duckdb").unlink()
    assert download_state(BUCKET, s3=s3) is True
    assert (tmp_path / "warehouse.duckdb").read_bytes() == b"snapshot history"
