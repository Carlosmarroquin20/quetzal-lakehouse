{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_buyer/dim_buyer.parquet"
    )
}}

with processes as (

    select * from {{ ref('stg_guatecompras__processes') }}

),

-- A buyer is described in every process it publishes. The most recent
-- description is kept; earlier names are not.
buyers as (

    select
        buyer_id,
        arg_max(buyer_name, updated_at) as buyer_name,
        arg_max(entity_code, updated_at) as entity_code,
        arg_max(entity_type, updated_at) as entity_type,
        arg_max(entity_sector, updated_at) as entity_sector
    from processes
    group by buyer_id

)

select
    {{ dbt_utils.generate_surrogate_key(['buyer_id']) }} as buyer_key,
    buyer_id,
    buyer_name,
    entity_code,
    -- Points to the budget entity, so procurement can be compared with the
    -- budget. Empty for buyers whose processes never name their entity.
    case
        when entity_code is not null
            then {{ dbt_utils.generate_surrogate_key(['entity_code']) }}
    end as entity_key,
    entity_type,
    entity_sector
from buyers
order by buyer_id
