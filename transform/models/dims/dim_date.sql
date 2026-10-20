-- Calendar dimension: one row per Central-time date covered by the grid data.
with bounds as (
    select
        min(cast(period_utc at time zone 'America/Chicago' as date)) as first_date,
        max(cast(period_utc at time zone 'America/Chicago' as date)) as last_date
    from {{ ref('int_grid__hourly_pivoted') }}
),

days as (
    select cast(unnest(generate_series(first_date, last_date, interval 1 day)) as date) as date_day
    from bounds
)

select
    cast(strftime(date_day, '%Y%m%d') as integer)  as date_key,
    date_day,
    year(date_day)                                  as year,
    quarter(date_day)                               as quarter,
    month(date_day)                                 as month,
    monthname(date_day)                             as month_name,
    dayofmonth(date_day)                            as day_of_month,
    isodow(date_day)                                as iso_day_of_week,
    dayname(date_day)                               as day_name,
    isodow(date_day) in (6, 7)                      as is_weekend,
    case
        when month(date_day) in (12, 1, 2) then 'Winter'
        when month(date_day) in (3, 4, 5)  then 'Spring'
        when month(date_day) in (6, 7, 8)  then 'Summer'
        else 'Fall'
    end                                             as season,
    date_trunc('month', date_day)::date             as month_start
from days
