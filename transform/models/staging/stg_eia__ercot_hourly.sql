{{ config(
    materialized = 'incremental',
    unique_key = 'period_utc',
    incremental_strategy = 'delete+insert',
    on_schema_change = 'append_new_columns'
) }}
-- One row per (hour, series type). Keeps the latest ingested value if a month was re-loaded.
with source as (
    select * from {{ source('raw', 'eia_ercot_hourly') }}
),

ranked as (
    select
        cast(period_utc as timestamptz)  as period_utc,
        upper(type)                      as series_type,
        cast(value_mwh as double)        as value_mwh,
        ingested_at,
        row_number() over (
            partition by period_utc, type
            order by ingested_at desc
        ) as rn
    from source
    where respondent = 'ERCO'
      and {{ incremental_filter('period_utc', partitioned=true) }}
)

select period_utc, series_type, value_mwh, ingested_at
from ranked
where rn = 1
