with source as (

    select * from {{ source('bronze_guatecompras', 'contracting_processes') }}

),

-- Only the fields named here are read from the record. Everything else,
-- including the contact details of people, stays in bronze.
parsed as (

    select
        ocid,
        json_transform(record, '{
            "compiledRelease": {
                "date": "VARCHAR",
                "buyer": {"id": "VARCHAR", "name": "VARCHAR"},
                "tender": {
                    "id": "VARCHAR",
                    "title": "VARCHAR",
                    "status": "VARCHAR",
                    "statusDetails": "VARCHAR",
                    "procurementMethod": "VARCHAR",
                    "procurementMethodDetails": "VARCHAR",
                    "mainProcurementCategory": "VARCHAR",
                    "datePublished": "VARCHAR",
                    "numberOfTenderers": "INTEGER"
                },
                "parties": [{
                    "id": "VARCHAR",
                    "name": "VARCHAR",
                    "identifier": {"scheme": "VARCHAR", "id": "VARCHAR"},
                    "details": {
                        "entityType": {"description": "VARCHAR"},
                        "type": {"description": "VARCHAR"}
                    }
                }]
            }
        }').compiledRelease as release,
        _source_file,
        _ingested_at
    from source

),

-- The source repeats a few processes. One row is kept per process: the most
-- recently updated one.
deduplicated as (

    select *
    from parsed
    qualify row_number() over (
        partition by ocid
        order by release.date::timestamptz desc, _ingested_at desc
    ) = 1

),

-- A buyer appears among the parties twice: as the budget entity it belongs
-- to (scheme GT-CISP) and as the purchasing unit (scheme GT-GCUC).
with_buyer_parties as (

    select
        *,
        list_filter(release.parties, party -> party.identifier.scheme = 'GT-CISP')[1] as entity,
        list_filter(release.parties, party -> party.identifier.scheme = 'GT-GCUC')[1] as purchasing_unit
    from deduplicated

)

select
    ocid,
    release.tender.id as tender_id,
    release.tender.title as title,
    release.tender.status as status,
    release.tender.statusDetails as status_details,
    release.tender.procurementMethod as procurement_method,
    release.tender.procurementMethodDetails as procurement_method_details,
    release.tender.mainProcurementCategory as procurement_category,
    release.tender.datePublished::timestamptz as published_at,
    -- The business date is the calendar day in Guatemala, whatever time zone
    -- the engine runs in.
    (release.tender.datePublished::timestamptz at time zone 'America/Guatemala')::date as published_date,
    release.tender.numberOfTenderers as number_of_tenderers,
    release.buyer.id as buyer_id,
    release.buyer.name as buyer_name,
    entity.identifier.id as entity_code,
    entity.details.entityType.description as entity_type,
    entity.details.type.description as entity_sector,
    purchasing_unit.id as purchasing_unit_id,
    purchasing_unit.name as purchasing_unit_name,
    release.date::timestamptz as updated_at,
    _source_file as source_file,
    _ingested_at as ingested_at
from with_buyer_parties
