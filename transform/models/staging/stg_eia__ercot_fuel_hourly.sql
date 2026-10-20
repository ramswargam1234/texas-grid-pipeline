{{ config(
    materialized = 'incremental',
    unique_key = 'period_utc',
    incremental_strategy = 'delete+insert',
    on_schema_change = 'append_new_columns'
) }}
-- One row per (hour, fuel type). Keeps the latest ingested value if a month was re-loaded.
with source as (
    select * from {{ source('raw', 'eia_ercot_fuel_hourly') }}
),

ranked as (
    select
        cast(period_utc as timestamptz)  as period_utc,
        upper(fuel_code)                 as fuel_code,
        fuel_name,
        cast(generation_mwh as double)   as generation_mwh,
        ingested_at,
        row_number() over (
            partition by period_utc, upper(fuel_code)
            order by ingested_at desc
        ) as rn
    from source
    where respondent = 'ERCO'
      and {{ incremental_filter('period_utc', partitioned=true) }}
)

select period_utc, fuel_code, fuel_name, generation_mwh, ingested_at
from ranked
where rn = 1
