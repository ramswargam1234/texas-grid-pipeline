-- Data-quality monitor: every hour in the covered range that has no demand value.
-- Real feeds have gaps; this makes them visible instead of silently skewing averages.
with bounds as (
    select min(period_utc) as start_ts, max(period_utc) as end_ts
    from {{ ref('int_grid__hourly_pivoted') }}
),

expected as (
    select unnest(generate_series(start_ts, end_ts, interval 1 hour)) as period_utc
    from bounds
),

actual as (
    select period_utc
    from {{ ref('int_grid__hourly_pivoted') }}
    where demand_mwh is not null
)

select
    e.period_utc,
    cast(e.period_utc at time zone 'America/Chicago' as date) as date_local
from expected e
left join actual a using (period_utc)
where a.period_utc is null
