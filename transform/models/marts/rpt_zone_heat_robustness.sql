-- Does each zone's heat-trend verdict survive EIA's known zone data issue?
-- EIA's 2025 zone figures add up to 4-5% more than ERCOT's total (documented in the README).
-- The same method is rerun two more ways, and a verdict counts as robust only if all three agree:
--   1. As reported      the zone data straight from EIA
--   2. Reconciled       each hour's zone values scaled so the 8 zones add up to ERCOT's total
--   3. Issue year out   the year with the known issue left out
with reconciled_hourly as (
    select
        z.zone_code, z.zone_label, z.date_local, z.zone_temp_f,
        z.demand_mwh * g.demand_mwh / nullif(sum(z.demand_mwh) over (partition by z.period_utc), 0) as demand_mwh
    from {{ ref('fct_zone_hourly') }} z
    join {{ ref('int_grid__hourly_pivoted') }} g using (period_utc)
    where g.demand_mwh > 0
),

reconciled_trend as (
    {{ zone_heat_trend('reconciled_hourly') }}
),

as_reported as (
    {{ zone_heat_change(ref('agg_zone_heat_trend')) }}
),

reconciled as (
    {{ zone_heat_change('reconciled_trend') }}
),

issue_year_out as (
    {{ zone_heat_change('(select * from ' ~ ref('agg_zone_heat_trend') ~ ' where year <> ' ~ var('zone_data_issue_year') ~ ')') }}
)

select
    a.zone_code,
    a.zone_label,
    a.first_year,
    a.latest_year,
    a.change_pct_points                          as change_as_reported,
    r.change_pct_points                          as change_reconciled,
    x.change_pct_points                          as change_issue_year_out,
    a.verdict                                    as verdict_as_reported,
    r.verdict                                    as verdict_reconciled,
    x.verdict                                    as verdict_issue_year_out,
    a.verdict = r.verdict and a.verdict = x.verdict as is_robust
from as_reported a
left join reconciled r using (zone_code)
left join issue_year_out x using (zone_code)
