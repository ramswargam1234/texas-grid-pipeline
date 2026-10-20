-- One row per year: how clean ERCOT's generation was, and the big four sources' shares.
with hourly as (
    select year(date_local) as year, fuel_key, is_renewable, is_carbon_free,
           greatest(generation_mwh, 0) as mwh
    from {{ ref('fct_fuel_hourly') }}
)

select
    year,
    count(distinct fuel_key)                                         as fuel_types,
    sum(mwh) / 1e6                                                   as generation_twh,
    sum(mwh) filter (where is_renewable)   / nullif(sum(mwh), 0)     as renewable_share,
    sum(mwh) filter (where is_carbon_free) / nullif(sum(mwh), 0)     as carbon_free_share,
    sum(mwh) filter (where fuel_key = 'WND') / nullif(sum(mwh), 0)   as wind_share,
    sum(mwh) filter (where fuel_key in ('SUN', 'SNB')) / nullif(sum(mwh), 0) as solar_share,
    sum(mwh) filter (where fuel_key = 'NG')  / nullif(sum(mwh), 0)   as gas_share,
    sum(mwh) filter (where fuel_key = 'COL') / nullif(sum(mwh), 0)   as coal_share
from hourly
group by year
