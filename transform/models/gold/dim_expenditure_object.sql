{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_expenditure_object/dim_expenditure_object.parquet"
    )
}}

-- What the money is spent on, in the national object-of-expenditure
-- classifier: one row per expenditure item, with the subgroup and group it
-- belongs to. Names come from the most recent fiscal year.

select
    {{ dbt_utils.generate_surrogate_key(['expenditure_item_code']) }} as expenditure_object_key,
    expenditure_item_code,
    arg_max(expenditure_item_name, fiscal_year) as expenditure_item_name,
    arg_max(expenditure_subgroup_code, fiscal_year) as expenditure_subgroup_code,
    arg_max(expenditure_subgroup_name, fiscal_year) as expenditure_subgroup_name,
    arg_max(expenditure_group_code, fiscal_year) as expenditure_group_code,
    arg_max(expenditure_group_name, fiscal_year) as expenditure_group_name
from {{ ref('stg_minfin__central_government_expenditure') }}
group by expenditure_item_code
order by expenditure_item_code
