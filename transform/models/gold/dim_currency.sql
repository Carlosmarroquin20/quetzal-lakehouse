{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_currency/dim_currency.parquet"
    )
}}

select
    {{ dbt_utils.generate_surrogate_key(['currency_code']) }} as currency_key,
    currency_code,
    currency_name
from {{ ref('currencies') }}
order by currency_code
