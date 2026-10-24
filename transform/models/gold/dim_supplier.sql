-- Gold is the layer others consume, so it does not identify natural persons.
-- Their tax number and name are replaced; so are those of suppliers whose
-- legal type is unknown, since they could be persons too. Companies and other
-- legal entities keep theirs. The key is a keyed hash (pseudonymize), so it
-- cannot be turned back into a tax number, yet every award of the same
-- supplier still shares it.

with suppliers as (

    select
        *,
        legal_type = 'INDIVIDUAL' as is_natural_person
    from {{ ref('stg_guatecompras__suppliers') }}

)

select
    pseudonymize(supplier_id) as supplier_key,
    case when is_natural_person = false then supplier_id end as supplier_id,
    case
        when is_natural_person = false then supplier_name
        when is_natural_person then 'Natural person'
        else 'Supplier of unknown legal type'
    end as supplier_name,
    identifier_scheme,
    legal_type,
    is_natural_person,
    is_natural_person is distinct from false as is_masked
from suppliers
order by supplier_key
