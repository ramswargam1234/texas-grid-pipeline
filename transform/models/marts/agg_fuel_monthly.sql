-- Monthly generation and share per fuel type (Central-time months).
with monthly as (
    select
        date_trunc('month', date_local)::date   as month,
        fuel_key,
        any_value(fuel_label)                   as fuel_label,
        any_value(fuel_group)                   as fuel_group,
        sum(greatest(generation_mwh, 0))        as generation_mwh,
        count(*)                                as hours
    from {{ ref('fct_fuel_hourly') }}
    group by 1, 2
)

select
    month, fuel_key, fuel_label, fuel_group, hours,
    generation_mwh / 1000                                                  as generation_gwh,
    generation_mwh / nullif(sum(generation_mwh) over (partition by month), 0) as share
from monthly
