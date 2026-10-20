-- Series dimension: what each EIA hourly series code means.
select series_code as series_key, series_name, description, unit
from {{ ref('ercot_series') }}
