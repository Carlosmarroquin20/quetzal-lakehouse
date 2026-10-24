-- Where the money is spent: one row per municipality, with its department.
-- Municipality codes are unique across departments. Besides real places, the
-- budget uses a few codes for spending without a single location.

select
    {{ dbt_utils.generate_surrogate_key(['municipality_code']) }} as geography_key,
    municipality_code,
    arg_max(municipality_name, fiscal_year) as municipality_name,
    arg_max(department_code, fiscal_year) as department_code,
    arg_max(department_name, fiscal_year) as department_name
from {{ ref('stg_minfin__central_government_expenditure') }}
group by municipality_code
order by municipality_code
