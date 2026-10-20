-- Every time EIA revised a day's published total: before and after values, and when we saw the change.
with versions as (
    select
        date_local,
        series_key,
        total_mwh,
        hours_reported,
        dbt_valid_from,
        lag(total_mwh)      over w as previous_total_mwh,
        lag(hours_reported) over w as previous_hours_reported
    from {{ ref('snp_eia_daily_totals') }}
    window w as (partition by snapshot_key order by dbt_valid_from)
)

select
    date_local,
    series_key,
    previous_total_mwh,
    total_mwh                                  as revised_total_mwh,
    total_mwh - previous_total_mwh             as change_mwh,
    previous_hours_reported,
    hours_reported                             as revised_hours_reported,
    dbt_valid_from                             as detected_at
from versions
where previous_total_mwh is not null
