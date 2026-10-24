with source as (

    select * from {{ source('bronze_banguat', 'exchange_rates') }}

),

typed as (

    -- The casts are strict on purpose: a date or number the source writes in
    -- an unexpected way stops the build instead of becoming a silent null.
    select
        strptime(fecha, '%d/%m/%Y')::date as rate_date,
        case moneda when '2' then 'USD' end as currency_code,
        compra::decimal(10, 6) as buy_rate,
        venta::decimal(10, 6) as sell_rate,
        _source_file as source_file,
        _ingested_at as ingested_at
    from source

)

select * from typed
order by rate_date
