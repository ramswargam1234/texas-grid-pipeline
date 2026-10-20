-- First vs latest reliable year per zone, with a verdict. Logic: macros/zone_heat.sql.
{{ zone_heat_change(ref('agg_zone_heat_trend')) }}
