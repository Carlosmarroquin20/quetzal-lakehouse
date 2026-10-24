with source as (

    select * from {{ source('bronze_guatecompras', 'contracting_processes') }}

),

-- Of each supplier only its identifier, name and legal type are read.
-- Addresses, emails and phone numbers stay in bronze.
parsed as (

    select
        json_transform(record, '{
            "compiledRelease": {
                "date": "VARCHAR",
                "awards": [{"suppliers": [{"id": "VARCHAR", "name": "VARCHAR"}]}],
                "parties": [{
                    "id": "VARCHAR",
                    "roles": ["VARCHAR"],
                    "details": {"legalEntityTypeDetail": {"description": "VARCHAR"}}
                }]
            }
        }').compiledRelease as release
    from source

),

-- Every award names its supplier, so this covers every supplier that was
-- awarded something. Bidders that never won and members of award committees
-- are left out.
awarded as (

    select
        supplier.id as supplier_id,
        supplier.name as supplier_name,
        release.date::timestamptz as updated_at
    from parsed, unnest(release.awards) as awards (award), unnest(award.suppliers) as suppliers (supplier)

),

-- The legal type is only given in the list of parties, which a few
-- processes leave incomplete.
described as (

    select
        party.id as supplier_id,
        party.details.legalEntityTypeDetail.description as legal_type,
        release.date::timestamptz as updated_at
    from parsed, unnest(release.parties) as parties (party)
    where list_contains(party.roles, 'supplier')

),

-- A supplier is named in every process it wins, sometimes with a different
-- spelling. The most recent one is kept.
latest_name as (

    select
        supplier_id,
        arg_max(supplier_name, updated_at) as supplier_name,
        max(updated_at) as updated_at
    from awarded
    group by supplier_id

),

latest_legal_type as (

    select
        supplier_id,
        arg_max(legal_type, updated_at) as legal_type
    from described
    group by supplier_id

)

select
    latest_name.supplier_id,
    latest_name.supplier_name,
    -- The identifier starts with the registry that issued it: GT-NIT for the
    -- tax registry, GT-GCID for suppliers without a tax number.
    regexp_extract(latest_name.supplier_id, '^([A-Z]+-[A-Z]+)-', 1) as identifier_scheme,
    latest_legal_type.legal_type,
    latest_name.updated_at
from latest_name
left join latest_legal_type
    on latest_legal_type.supplier_id = latest_name.supplier_id
