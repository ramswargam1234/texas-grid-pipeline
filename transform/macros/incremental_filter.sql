{#
  Incremental window for the big hourly tables.

  On an incremental run, a model only re-processes hours from (latest hour already loaded - N days) onward,
  where N = var('incremental_lookback_days'). The lookback is what handles late and revised data:
    - EIA revises recent hours, and the ingestion layer re-loads months younger than 45 days;
    - the weather archive trails by ~6 days, so a grid hour first loaded without weather gets it on a later run.
  Rows in the window are replaced (delete+insert on period_utc), so re-running is idempotent.

  partitioned=true also filters on the lake's hive partitions (year=YYYY/month=MM, UTC months). The cutoff is
  computed first and inlined as a constant, so DuckDB skips the older Parquet files entirely, which matters
  most when reading from S3.

  On a first run or with --full-refresh this returns `true` and the model reads everything.
#}
{% macro incremental_filter(time_col='period_utc', partitioned=false) -%}
  {#- unit tests have no real table (this is none): treat them as a full build -#}
  {%- if execute and this is not none and is_incremental() -%}
    {%- set q -%}
      select strftime(max(period_utc) at time zone 'UTC' - interval {{ var('incremental_lookback_days') }} day,
                      '%Y-%m-%d %H:%M:%S')
      from {{ this }}
    {%- endset -%}
    {%- set cutoff = run_query(q).columns[0].values()[0] -%}
    {%- if cutoff -%}
      cast({{ time_col }} as timestamptz) >= timestamptz '{{ cutoff }}+00'
      {%- if partitioned %} and (year * 100 + cast(month as integer)) >= {{ cutoff[:4] }}{{ cutoff[5:7] }}{% endif -%}
    {%- else -%}
      true
    {%- endif -%}
  {%- else -%}
    true
  {%- endif -%}
{%- endmacro %}
