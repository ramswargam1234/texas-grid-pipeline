-- The load-shed window is 72 hour-starting timestamps. Warn if demand data is missing for any of them,
-- because the unserved-energy totals would then be understated.
{{ config(severity = 'warn') }}
select shed_hours, shed_hours_with_data
from {{ ref('agg_uri_summary') }}
where shed_hours_with_data < 72
