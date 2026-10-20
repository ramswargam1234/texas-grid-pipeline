-- One row per zone: heat sensitivity in the first vs the latest reliable year, and whether the
-- change is clear (95% confidence intervals don't overlap) or could be noise.
with reliable as (
    select * from {{ ref('agg_zone_heat_trend') }}
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
