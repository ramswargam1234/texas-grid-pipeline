-- How each ERCOT weather zone's heat sensitivity changes year by year.
-- Uses DAILY averages on hot days (zone's daily average temperature >= 75°F): one point per day keeps
-- the confidence interval honest, because neighbouring hours are not independent observations.
-- Slope = extra daily-average demand per +1°F, also shown as % of the zone's average demand that year.
with daily as (
    select
        zone_code,
        any_value(zone_label)    as zone_label,
        year(date_local)         as year,
        date_local,
        avg(demand_mwh)          as demand_mwh,
        avg(zone_temp_f)         as temp_f,
        count(*)                 as hours
    from {{ ref('fct_zone_hourly') }}
    where demand_mwh is not null and zone_temp_f is not null
    group by zone_code, date_local
    having count(*) >= 20        -- skip partial days
),

yearly_avg as (
    select zone_code, year, avg(demand_mwh) as avg_demand_mwh, count(*) as days
    from daily
    group by 1, 2
),

fit as (
    select
        zone_code,
        any_value(zone_label)               as zone_label,
        year,
        regr_count(demand_mwh, temp_f)      as hot_days,
        regr_slope(demand_mwh, temp_f)      as slope_mwh_per_f,
        regr_r2(demand_mwh, temp_f)         as r2,
        regr_sxx(demand_mwh, temp_f)        as sxx,
        regr_syy(demand_mwh, temp_f)        as syy,
        regr_sxy(demand_mwh, temp_f)        as sxy,
        avg(temp_f)                         as avg_hot_day_temp_f
    from daily
    where temp_f >= 75
    group by zone_code, year
),

with_se as (
    select
        *,
        -- Standard error of the slope: sqrt(residual SS / (n - 2) / Sxx).
        case when hot_days > 2 and sxx > 0
             then sqrt(greatest(syy - sxy * sxy / sxx, 0) / (hot_days - 2) / sxx) end as slope_se
    from fit
)

select
    f.zone_code,
    f.zone_label,
    f.year,
    a.days,
    f.hot_days,
    f.hot_days >= 30                                         as is_reliable,
    f.avg_hot_day_temp_f,
    -- Rounded to 4 decimals: plenty for MWh and % per °F, and stable across platforms.
    round(f.slope_mwh_per_f, 4)                                       as slope_mwh_per_f,
    round(f.slope_se, 4)                                              as slope_se,
    round(f.slope_mwh_per_f - 1.96 * f.slope_se, 4)                   as ci_low_mwh_per_f,
    round(f.slope_mwh_per_f + 1.96 * f.slope_se, 4)                   as ci_high_mwh_per_f,
    round(100 * f.slope_mwh_per_f / a.avg_demand_mwh, 4)              as slope_pct_per_f,
    round(100 * (f.slope_mwh_per_f - 1.96 * f.slope_se) / a.avg_demand_mwh, 4) as ci_low_pct_per_f,
    round(100 * (f.slope_mwh_per_f + 1.96 * f.slope_se) / a.avg_demand_mwh, 4) as ci_high_pct_per_f,
    f.r2
from with_se f
join yearly_avg a using (zone_code, year)
