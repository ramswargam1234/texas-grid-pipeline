-- One row per (hour, ERCOT weather zone). Keeps the latest ingested value if a month was re-loaded.
with source as (
    select * from {{ source('raw', 'eia_ercot_zone_hourly') }}
),

ranked as (
    select
        cast(period_utc as timestamptz)  as period_utc,
        upper(zone_code)                 as zone_code,
        zone_name,
        cast(demand_mwh as double)       as demand_mwh,
        ingested_at,
        row_number() over (
            partition by period_utc, zone_code
            order by ingested_at desc
        ) as rn
    from source
    where parent = 'ERCO'
)

select period_utc, zone_code, zone_name, demand_mwh, ingested_at
from ranked
where rn = 1
