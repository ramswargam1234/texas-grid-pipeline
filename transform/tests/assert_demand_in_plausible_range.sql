-- ERCOT hourly demand has historically sat roughly between 25,000 and 90,000 MWh.
-- Values far outside that range usually mean a unit or feed error. Warn, don't block.
{{ config(severity = 'warn') }}
select period_utc, demand_mwh
from {{ ref('fct_grid_hourly') }}
where demand_mwh is not null
  and (demand_mwh < 15000 or demand_mwh > 100000)
