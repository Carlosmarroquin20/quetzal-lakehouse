{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/fct_awards/fct_awards.parquet"
    )
}}

with awards as (

    select * from {{ ref('stg_guatecompras__awards') }}

),

processes as (

    select * from {{ ref('stg_guatecompras__processes') }}

),

usd_rates as (

    select
        rates.date_key,
        rates.reference_rate
    from {{ ref('fct_exchange_rates') }} as rates
    inner join {{ ref('dim_currency') }} as currencies
        on currencies.currency_key = rates.currency_key
    where currencies.currency_code = 'USD'

),

-- The award brings the supplier, the amount and its date; the process it
-- belongs to brings the buyer and how the purchase was made.
described as (

    select
        awards.award_id,
        awards.ocid,
        processes.tender_id,
        strftime(awards.awarded_date, '%Y%m%d')::integer as award_date_key,
        strftime(processes.published_date, '%Y%m%d')::integer as published_date_key,
        processes.buyer_id,
        awards.supplier_id,
        processes.procurement_method_details,
        processes.procurement_method,
        processes.procurement_category,
        awards.currency_code,
        awards.status = 'cancelled' as is_cancelled,
        awards.amount as awarded_amount,
        -- Only quetzales occur in the source. An award in another currency
        -- gets no amount here, and the not_null test on the column fails.
        case when awards.currency_code = 'GTQ' then awards.amount end as awarded_amount_gtq
    from awards
    inner join processes
        on processes.ocid = awards.ocid

)

select
    described.award_id,
    described.ocid,
    described.tender_id,
    described.award_date_key,
    described.published_date_key,
    {{ dbt_utils.generate_surrogate_key(['described.buyer_id']) }} as buyer_key,
    {{ dbt_utils.generate_surrogate_key(['described.supplier_id']) }} as supplier_key,
    {{ dbt_utils.generate_surrogate_key(['described.procurement_method_details', 'described.procurement_method']) }} as procurement_method_key,
    {{ dbt_utils.generate_surrogate_key(['described.currency_code']) }} as currency_key,
    described.procurement_category,
    described.is_cancelled,
    described.awarded_amount,
    described.awarded_amount_gtq,
    -- Converted with the reference rate of the day the award was made.
    round(described.awarded_amount_gtq / usd_rates.reference_rate, 2)::decimal(18, 2) as awarded_amount_usd
from described
left join usd_rates
    on usd_rates.date_key = described.award_date_key
