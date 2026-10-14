-- Joining awards to their process and to the exchange rate must neither drop
-- nor repeat an award. Row counts are compared by another test; this one
-- compares the money. Returns a row when the totals differ.

with gold as (

    select sum(awarded_amount) as total from {{ ref('fct_awards') }}

),

silver as (

    select sum(amount) as total from {{ ref('stg_guatecompras__awards') }}

)

select
    gold.total as gold_total,
    silver.total as silver_total
from gold
cross join silver
where gold.total is distinct from silver.total
