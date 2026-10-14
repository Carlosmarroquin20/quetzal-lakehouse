-- The fact table must have one row for every calendar day between the first
-- and the last day of each currency. Returns the currencies where the number
-- of rows and the number of days differ.

select
    facts.currency_key,
    count(*) as row_count,
    datediff('day', min(dates.date_day), max(dates.date_day)) + 1 as days_in_range
from {{ ref('fct_exchange_rates') }} as facts
inner join {{ ref('dim_date') }} as dates
    on dates.date_key = facts.date_key
group by facts.currency_key
having count(*) <> datediff('day', min(dates.date_day), max(dates.date_day)) + 1
