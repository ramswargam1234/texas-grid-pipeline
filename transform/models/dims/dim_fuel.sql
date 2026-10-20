-- Fuel type dimension: what each EIA fuel code means and how it is grouped.
select fuel_code as fuel_key, fuel_label, fuel_group, is_renewable, is_carbon_free, sort_order
from {{ ref('ercot_fuel_types') }}
