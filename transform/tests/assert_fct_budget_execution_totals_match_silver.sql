-- The budget fact table must carry exactly the money of silver, year by year.
-- Returns the fiscal years where any total differs.

with gold as (

    select fiscal_year, sum(current_budget) as current_budget, sum(accrued) as accrued, sum(paid) as paid
    from {{ ref('fct_budget_execution') }}
    group by fiscal_year

),

silver as (

    select fiscal_year, sum(current_budget) as current_budget, sum(accrued) as accrued, sum(paid) as paid
    from {{ ref('stg_minfin__central_government_expenditure') }}
    group by fiscal_year

)

select
    coalesce(gold.fiscal_year, silver.fiscal_year) as fiscal_year,
    gold.accrued as gold_accrued,
    silver.accrued as silver_accrued
from gold
full outer join silver
    on silver.fiscal_year = gold.fiscal_year
where gold.current_budget is distinct from silver.current_budget
   or gold.accrued is distinct from silver.accrued
   or gold.paid is distinct from silver.paid
