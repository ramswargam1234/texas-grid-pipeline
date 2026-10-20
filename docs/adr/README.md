# Architecture Decision Records

Short records of the main design decisions: the context, what was chosen, what else was considered, and the
trade-offs that were accepted.

| ADR | Decision |
|---|---|
| [0001](0001-duckdb-and-dbt-as-warehouse.md) | DuckDB + dbt as the warehouse |
| [0002](0002-partitioned-parquet-lake-monthly-overwrite.md) | Parquet lake, one file per month, overwritten on reload (idempotent, resumable loads) |
| [0003](0003-utc-storage-central-reporting.md) | Store in UTC, report in US Central time |
| [0004](0004-airflow-locally-github-actions-in-cloud.md) | Airflow locally, GitHub Actions for the scheduled cloud run |
| [0005](0005-dashboard-from-committed-snapshot.md) | Public dashboard reads a committed CSV snapshot |
| [0006](0006-warehouse-state-in-s3-for-snapshots.md) | Warehouse file kept in S3 so dbt snapshots persist |
| [0007](0007-terraform-import-and-iam.md) | Terraform with import blocks; least-privilege IAM |
| [0008](0008-testing-strategy.md) | Unit, data and reconciliation tests with deliberate severities |
| [0009](0009-uri-unserved-demand-method.md) | Method for estimating unserved demand during Winter Storm Uri |
| [0010](0010-incremental-models-with-lookback.md) | Incremental hourly models with a 45-day lookback for late and revised data |

Format: Status, Context, Decision, Alternatives considered, Consequences. A superseded decision gets a new ADR
rather than an edit, so the history of the reasoning is kept.
