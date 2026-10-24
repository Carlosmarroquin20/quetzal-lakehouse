with methods as (

    select distinct
        procurement_method_details,
        procurement_method
    from {{ ref('stg_guatecompras__processes') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['procurement_method_details', 'procurement_method']) }} as procurement_method_key,
    procurement_method_details as procurement_procedure,
    procurement_method as ocds_method
from methods
order by procurement_procedure
