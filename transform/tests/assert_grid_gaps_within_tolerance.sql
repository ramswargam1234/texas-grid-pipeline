-- Real feeds have small gaps. Warn on any missing hour; fail if more than 10 days (240 h) are missing.
{{ config(severity = 'error', warn_if = '>0', error_if = '>240') }}
select * from {{ ref('dq_grid_missing_hours') }}
