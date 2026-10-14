-- The days gold fills in must be exactly the days the source is known to
-- skip. Returns any day that is on one side and not on the other.

with filled_days as (

    select dates.date_day
    from {{ ref('fct_exchange_rates') }} as facts
    inner join {{ ref('dim_date') }} as dates
        on dates.date_key = facts.date_key
    where not facts.is_published

),

known_days as (

    select missing_date as date_day
    from {{ ref('banguat_known_missing_dates') }}

)

select
    coalesce(filled_days.date_day, known_days.date_day) as date_day,
    filled_days.date_day is not null as is_filled_in_gold,
    known_days.date_day is not null as is_known_missing
from filled_days
full outer join known_days
    on known_days.date_day = filled_days.date_day
where filled_days.date_day is null
   or known_days.date_day is null
