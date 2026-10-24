-- Where the money comes from: taxes, loans, donations and so on.

select
    {{ dbt_utils.generate_surrogate_key(['funding_source_code']) }} as funding_source_key,
    funding_source_code,
    arg_max(funding_source_name, fiscal_year) as funding_source_name
from {{ ref('stg_minfin__central_government_expenditure') }}
group by funding_source_code
order by funding_source_code
