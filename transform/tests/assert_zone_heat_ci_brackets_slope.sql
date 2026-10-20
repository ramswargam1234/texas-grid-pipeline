-- Every confidence interval must contain its own slope (catches a sign or formula mistake).
select zone_code, year, ci_low_pct_per_f, slope_pct_per_f, ci_high_pct_per_f
from {{ ref('agg_zone_heat_trend') }}
where slope_se is not null
  and not (ci_low_pct_per_f <= slope_pct_per_f and slope_pct_per_f <= ci_high_pct_per_f)
