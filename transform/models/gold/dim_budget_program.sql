{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_budget_program/dim_budget_program.parquet"
    )
}}

-- The programmatic structure of the budget: who executes the money and in
-- which program, subprogram, project, activity and work. Codes below the
-- entity are only unique within it, so the whole path is the key. Names come
-- from the most recent fiscal year.

select
    {{ dbt_utils.generate_surrogate_key([
        'entity_code', 'executing_unit_code', 'program_code', 'subprogram_code',
        'project_code', 'activity_code', 'work_code'
    ]) }} as budget_program_key,
    entity_code,
    executing_unit_code,
    arg_max(executing_unit_name, fiscal_year) as executing_unit_name,
    program_code,
    arg_max(program_name, fiscal_year) as program_name,
    subprogram_code,
    arg_max(subprogram_name, fiscal_year) as subprogram_name,
    project_code,
    arg_max(project_name, fiscal_year) as project_name,
    activity_code,
    arg_max(activity_name, fiscal_year) as activity_name,
    work_code,
    arg_max(work_name, fiscal_year) as work_name
from {{ ref('stg_minfin__central_government_expenditure') }}
group by
    entity_code,
    executing_unit_code,
    program_code,
    subprogram_code,
    project_code,
    activity_code,
    work_code
order by
    entity_code,
    executing_unit_code,
    program_code,
    subprogram_code,
    project_code,
    activity_code,
    work_code
