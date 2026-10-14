{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/fct_exchange_rates/fct_exchange_rates.parquet"
    )
}}

with rates as (

    select * from {{ ref('stg_banguat__exchange_rates') }}

),

published_range as (

    select
        currency_code,
        min(rate_date) as first_date,
        max(rate_date) as last_date
    from rates
    group by currency_code

),

-- One row per currency and calendar day, whether or not the source
-- published a rate for it.
calendar as (

    select
        published_range.currency_code,
        dates.date_key,
        dates.date_day
    from published_range
    inner join {{ ref('dim_date') }} as dates
        on dates.date_day between published_range.first_date and published_range.last_date

),

-- A day without a published rate takes the last rate published before it.
filled as (

    select
        calendar.date_key,
        calendar.currency_code,
        rates.rate_date is not null as is_published,
        last_value(rates.rate_date ignore nulls) over rate_history as rate_published_date,
        last_value(rates.buy_rate ignore nulls) over rate_history as buy_rate,
        last_value(rates.sell_rate ignore nulls) over rate_history as sell_rate
    from calendar
    left join rates
        on rates.currency_code = calendar.currency_code
        and rates.rate_date = calendar.date_day
    window rate_history as (
        partition by calendar.currency_code
        order by calendar.date_day
        rows between unbounded preceding and current row
    )

)

select
    filled.date_key,
    currencies.currency_key,
    filled.buy_rate,
    filled.sell_rate,
    -- Midpoint of both rates. Multiplying by 0.5 keeps the result an exact
    -- decimal; dividing would turn it into a floating point number.
    ((filled.buy_rate + filled.sell_rate) * 0.5)::decimal(11, 7) as reference_rate,
    filled.is_published,
    filled.rate_published_date
from filled
inner join {{ ref('dim_currency') }} as currencies
    on currencies.currency_code = filled.currency_code
order by filled.date_key
