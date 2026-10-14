-- Every calendar day between the first and the last rate must have a row,
-- except the days the source is known to omit. Returns the days that break
-- that rule, so a new gap fails the build.

with rates as (

    select rate_date from {{ ref('stg_banguat__exchange_rates') }}

),

calendar as (

    select unnest(generate_series(min(rate_date), max(rate_date), interval 1 day))::date as calendar_date
    from rates

)

select calendar_date
from calendar
where calendar_date not in (select rate_date from rates)
  and calendar_date not in (select missing_date from {{ ref('banguat_known_missing_dates') }})
