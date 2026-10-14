{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/fct_budget_execution/fct_budget_execution.parquet"
    )
}}

-- One row per budget line and fiscal year, the grain of the source. The
-- classifiers with a hierarchy or names of their own become dimensions. The
-- three that are only a code and a name on each line (budget type, economic
-- class and lending organism) stay here as degenerate attributes, with the
-- correlative that completes the key of the line.

select
    fiscal_year,
    {{ dbt_utils.generate_surrogate_key(['entity_code']) }} as entity_key,
    {{ dbt_utils.generate_surrogate_key([
        'entity_code', 'executing_unit_code', 'program_code', 'subprogram_code',
        'project_code', 'activity_code', 'work_code'
    ]) }} as budget_program_key,
    {{ dbt_utils.generate_surrogate_key(['expenditure_item_code']) }} as expenditure_object_key,
    {{ dbt_utils.generate_surrogate_key(['funding_source_code']) }} as funding_source_key,
    {{ dbt_utils.generate_surrogate_key(['municipality_code']) }} as geography_key,
    budget_type_code,
    budget_type_name,
    economic_code,
    economic_name,
    organism_code,
    organism_name,
    correlative,
    initial_budget,
    budget_changes,
    current_budget,
    pre_committed,
    committed,
    accrued,
    paid
from {{ ref('stg_minfin__central_government_expenditure') }}
