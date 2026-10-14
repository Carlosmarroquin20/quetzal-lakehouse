-- The list of accepted gaps must not go stale. If the source starts
-- publishing one of those days, this returns it, and the day has to be
-- removed from the seed.

select known.missing_date
from {{ ref('banguat_known_missing_dates') }} as known
inner join {{ ref('stg_banguat__exchange_rates') }} as rates
    on rates.rate_date = known.missing_date
