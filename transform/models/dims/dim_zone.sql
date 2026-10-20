-- ERCOT weather zone dimension, plus one 'ERCO' row for the whole grid.
with zones as (
    select
        zone_code,
        any_value(zone_label)                                   as zone_label,
        string_agg(weather_city, ', ' order by weather_city)    as weather_cities,
        count(*)                                                as weather_city_count
    from {{ ref('ercot_zone_cities') }}
    group by zone_code
)

select zone_code as zone_key, zone_label, weather_cities, weather_city_count, false as is_system_total
from zones
union all
select 'ERCO', 'ERCOT (whole grid)', 'austin, dallas, houston, san_antonio', 4, true
