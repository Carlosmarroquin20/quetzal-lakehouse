with source as (

    select * from {{ source('bronze_guatecompras', 'contracting_processes') }}

),

parsed as (

    select
        ocid,
        json_transform(record, '{
            "compiledRelease": {
                "date": "VARCHAR",
                "awards": [{
                    "id": "VARCHAR",
                    "status": "VARCHAR",
                    "statusDetails": "VARCHAR",
                    "date": "VARCHAR",
                    "value": {"amount": "DECIMAL(18,2)", "currency": "VARCHAR"},
                    "suppliers": [{"id": "VARCHAR"}]
                }]
            }
        }').compiledRelease as release,
        _source_file,
        _ingested_at
    from source

),

-- Same rule as in stg_guatecompras__processes, so that both models keep the
-- same version of a repeated process.
deduplicated as (

    select *
    from parsed
    qualify row_number() over (
        partition by ocid
        order by release.date::timestamptz desc, _ingested_at desc
    ) = 1

),

-- One row per award. A process without awards produces no rows.
awards as (

    select
        ocid,
        unnest(release.awards) as award,
        _source_file,
        _ingested_at
    from deduplicated

)

select
    award.id as award_id,
    ocid,
    award.status as status,
    award.statusDetails as status_details,
    award.date::timestamptz as awarded_at,
    (award.date::timestamptz at time zone 'America/Guatemala')::date as awarded_date,
    award.value.amount as amount,
    award.value.currency as currency_code,
    -- The source gives every award exactly one supplier; a test checks it.
    award.suppliers[1].id as supplier_id,
    len(award.suppliers) as supplier_count,
    _source_file as source_file,
    _ingested_at as ingested_at
from awards
