-- How much lower is demand on each holiday than on a normal day?
-- Baseline = the same weekday 1 and 2 weeks before and after (4 days), skipping any that are holidays.
-- Comparing to the same weekday nearby controls for day of week and season; the temperature difference
-- is shown so a holiday that happened to be much hotter or colder than its baseline can be spotted.
with daily as (
    select a.date_local, a.avg_demand_mwh, a.avg_temp_f, a.hours_with_demand,
           d.is_holiday, d.holiday_name, d.holiday_type, d.is_nerc_holiday, d.day_name
    from {{ ref('agg_grid_daily') }} a
    join {{ ref('dim_date') }} d on d.date_day = a.date_local
    where a.hours_with_demand >= 20
),

holiday_days as (
    select * from daily where is_holiday
),

baseline as (
    select
        h.date_local,
        avg(b.avg_demand_mwh)   as baseline_demand_mwh,
        avg(b.avg_temp_f)       as baseline_temp_f,
        count(*)                as baseline_days
    from holiday_days h
    join daily b
      on b.date_local in (h.date_local - 14, h.date_local - 7, h.date_local + 7, h.date_local + 14)
     and not b.is_holiday
    group by h.date_local
)

select
    h.date_local,
    year(h.date_local)                                              as year,
    h.holiday_name,
    h.holiday_type,
    h.is_nerc_holiday,
    h.day_name,
    h.avg_demand_mwh,
    b.baseline_demand_mwh,
    b.baseline_days,
    round(100 * (h.avg_demand_mwh - b.baseline_demand_mwh) / b.baseline_demand_mwh, 2) as demand_change_pct,
    round(h.avg_temp_f - b.baseline_temp_f, 1)                      as temp_diff_f
from holiday_days h
join baseline b using (date_local)
where b.baseline_days >= 2
