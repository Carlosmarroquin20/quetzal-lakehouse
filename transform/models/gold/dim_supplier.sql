{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_supplier/dim_supplier.parquet"
    )
}}

select
    {{ dbt_utils.generate_surrogate_key(['supplier_id']) }} as supplier_key,
    supplier_id,
    supplier_name,
    identifier_scheme,
    legal_type,
    -- Unknown, not false, when the source does not give the legal type.
    legal_type = 'INDIVIDUAL' as is_natural_person
from {{ ref('stg_guatecompras__suppliers') }}
order by supplier_id
