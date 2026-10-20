-- One row per (zone, year) in the heat-sensitivity trend.
select zone_code, year, count(*) as n
from {{ ref('agg_zone_heat_trend') }}
group by 1, 2
having count(*) > 1
