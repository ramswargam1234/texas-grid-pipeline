{# Shared logic for the zone heat-sensitivity trend, so the same method can be rerun on
   different inputs (as reported, reconciled to ERCOT's total, one year left out). #}

{% macro zone_heat_trend(hourly) %}
-- How each ERCOT weather zone's heat sensitivity changes year by year.
-- Uses DAILY averages on hot days (zone's daily average temperature >= 75°F): one point per day keeps
-- the confidence interval honest, because neighbouring hours are not independent observations.
-- Slope = extra daily-average demand per +1°F, also shown as % of the zone's average demand that year.
-- `hourly` needs: zone_code, zone_label, date_local, demand_mwh, zone_temp_f.
with daily as (
    select
        zone_code,
        any_value(zone_label)    as zone_label,
        year(date_local)         as year,
        date_local,
        avg(demand_mwh)          as demand_mwh,
        avg(zone_temp_f)         as temp_f,
        count(*)                 as hours
    from {{ hourly }}
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
{% endmacro %}


{% macro zone_heat_change(trend) %}
-- One row per zone: heat sensitivity in the first vs the latest reliable year, and whether the
-- change is clear (95% confidence intervals don't overlap) or could be noise.
with reliable as (
    select * from {{ trend }}
    where is_reliable
),

ends as (
    select
        zone_code,
        any_value(zone_label)                                   as zone_label,
        min(year)                                               as first_year,
        max(year)                                               as latest_year,
        count(*)                                                as years
    from reliable
    group by zone_code
)

select
    e.zone_code, e.zone_label, e.first_year, e.latest_year, e.years,
    f.slope_pct_per_f                                           as first_pct_per_f,
    l.slope_pct_per_f                                           as latest_pct_per_f,
    l.slope_pct_per_f - f.slope_pct_per_f                       as change_pct_points,
    f.slope_mwh_per_f                                           as first_mwh_per_f,
    l.slope_mwh_per_f                                           as latest_mwh_per_f,
    case
        when e.years < 2                                    then 'Not enough years'
        when l.ci_low_pct_per_f > f.ci_high_pct_per_f       then 'More heat-sensitive'
        when l.ci_high_pct_per_f < f.ci_low_pct_per_f       then 'Less heat-sensitive'
        else 'No clear change'
    end                                                         as verdict
from ends e
join reliable f on f.zone_code = e.zone_code and f.year = e.first_year
join reliable l on l.zone_code = e.zone_code and l.year = e.latest_year
{% endmacro %}
