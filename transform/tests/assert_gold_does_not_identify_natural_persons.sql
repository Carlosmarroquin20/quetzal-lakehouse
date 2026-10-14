-- Gold must not show the tax number or the name of a supplier that is, or
-- could be, a natural person. Silver holds the original values; each one is
-- matched to its gold row through the keyed hash. Returns every such
-- supplier whose identifier or name still appears in gold.

with persons as (

    -- The hash is computed once per supplier, before the join, so the join
    -- compares plain values.
    select
        supplier_id,
        supplier_name,
        pseudonymize(supplier_id) as supplier_key
    from {{ ref('stg_guatecompras__suppliers') }}
    where legal_type = 'INDIVIDUAL' or legal_type is null

)

select gold.supplier_key
from persons
inner join {{ ref('dim_supplier') }} as gold
    on gold.supplier_key = persons.supplier_key
where gold.supplier_id = persons.supplier_id
   or gold.supplier_name = persons.supplier_name
