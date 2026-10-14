-- A small share of processes (0.7 % when this was written) does not list the
-- budget entity of the buyer. That is accepted. A share above 2 % would mean
-- the source changed how it describes buyers, and fails the build.

select
    count(*) as processes,
    count(*) filter (where entity_code is null) as without_entity
from {{ ref('stg_guatecompras__processes') }}
having count(*) filter (where entity_code is null) > 0.02 * count(*)
