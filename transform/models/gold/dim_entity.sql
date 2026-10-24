-- Budget entities of the public sector, shared by the budget and procurement
-- facts. The budget data gives official names, but only for the central
-- government; every other entity is known only through the processes that
-- name it in Guatecompras.

with budget as (

    select
        entity_code,
        arg_max(entity_name, fiscal_year) as entity_name
    from {{ ref('stg_minfin__central_government_expenditure') }}
    group by entity_code

),

processes as (

    select * from {{ ref('stg_guatecompras__processes') }}
    where entity_code is not null

),

-- Several buyers can share an entity code, each with its own name. The name
-- used in most processes stands for the entity; a tie goes to the first name
-- in alphabetical order.
procurement_names as (

    select
        entity_code,
        first(buyer_name order by processes desc, buyer_name) as entity_name
    from (
        select entity_code, buyer_name, count(*) as processes
        from processes
        group by entity_code, buyer_name
    )
    group by entity_code

),

procurement as (

    select
        processes.entity_code,
        any_value(procurement_names.entity_name) as entity_name,
        arg_max(processes.entity_type, processes.updated_at) as entity_type,
        arg_max(processes.entity_sector, processes.updated_at) as entity_sector
    from processes
    inner join procurement_names
        on procurement_names.entity_code = processes.entity_code
    group by processes.entity_code

),

entities as (

    select
        coalesce(budget.entity_code, procurement.entity_code) as entity_code,
        coalesce(budget.entity_name, procurement.entity_name) as entity_name,
        case
            when budget.entity_code is not null then 'MINFIN' else 'Guatecompras'
        end as name_source,
        procurement.entity_type,
        procurement.entity_sector,
        budget.entity_code is not null as has_budget_data,
        procurement.entity_code is not null as has_procurement_data
    from budget
    full outer join procurement
        on procurement.entity_code = budget.entity_code

)

select
    {{ dbt_utils.generate_surrogate_key(['entity_code']) }} as entity_key,
    entity_code,
    entity_name,
    name_source,
    entity_type,
    entity_sector,
    has_budget_data,
    has_procurement_data
from entities
order by entity_code
