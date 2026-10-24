select
    {{ dbt_utils.generate_surrogate_key(['currency_code']) }} as currency_key,
    currency_code,
    currency_name
from {{ ref('currencies') }}
order by currency_code
