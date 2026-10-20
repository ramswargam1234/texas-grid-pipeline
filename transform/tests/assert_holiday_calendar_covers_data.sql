-- The holiday seed must cover every year in the data. When this warns, extend it:
--   python -m src.holidays_seed --end <year>
{{ config(severity = 'warn') }}
select max(year) as last_data_year, (select max(year(holiday_date)) from {{ ref('us_holidays') }}) as last_holiday_year
from {{ ref('dim_date') }}
having max(year) > (select max(year(holiday_date)) from {{ ref('us_holidays') }})
