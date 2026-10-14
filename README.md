# quetzal-lakehouse

A financial lakehouse built on public data from Guatemala, organized in bronze,
silver and gold layers.

The project is built in small phases. This README describes only what exists
in the repository today; everything else is listed under
[Not built yet](#not-built-yet).

## Current state

- A Docker Compose stack with an S3-compatible object store and one bucket per
  layer built so far: `quetzal-bronze` and `quetzal-silver`.
- An ingestion job that lands the Banco de Guatemala exchange rate (quetzales
  per US dollar, one record per published day since November 1989) in the
  bronze bucket.
- A dbt project that turns the bronze records into a typed silver table and
  checks it with 17 data tests and one unit test.

There is no gold layer or data model yet.

## Architecture

```mermaid
flowchart LR
    banguat["Banco de Guatemala<br/>exchange rate web service<br/>(SOAP/XML)"]
    subgraph compose["Docker Compose"]
        ingestion["ingestion job<br/>(Python)"]
        transform["transform job<br/>(dbt + DuckDB)"]
        subgraph storage["storage: SeaweedFS S3 gateway, 127.0.0.1:8333"]
            bronze[("quetzal-bronze<br/>raw XML + Parquet<br/>one partition per year")]
            silver[("quetzal-silver<br/>typed Parquet")]
        end
    end
    banguat -- "one request per year" --> ingestion
    ingestion -- "write" --> bronze
    bronze -- "read" --> transform
    transform -- "write, then test" --> silver
```

## Getting started

Requirements: Docker with Compose v2.

1. Create your local configuration and replace the placeholder values:

   ```bash
   cp .env.example .env
   ```

2. Start the object store and wait until it is healthy:

   ```bash
   docker compose up -d --wait
   ```

3. Load the full exchange rate history into bronze:

   ```bash
   docker compose run --rm ingestion --from-year 1989
   ```

   The first run builds the job image. The load itself takes about ten
   seconds and logs one line per year with the number of records it stored.

4. Build the silver layer and run its tests:

   ```bash
   docker compose run --rm transform
   ```

   This runs `dbt build`. It should end with `PASS=20 ... ERROR=0`.

After the first load, running the ingestion job without arguments refreshes
the current year only:

```bash
docker compose run --rm ingestion
```

Running any of these commands again replaces the same objects. Nothing is
duplicated.

To check how old the bronze data is:

```bash
docker compose run --rm transform source freshness
```

The S3 endpoint is `http://localhost:8333`. Requests must be signed with the
key pair from `.env`; unsigned requests and wrong keys are rejected.

To stop the stack and keep the data:

```bash
docker compose down
```

Adding `-v` also deletes the volume, and with it every stored object.

## Bronze layout

Each year of the source is stored twice under `banguat/exchange_rates/`:

| Object | Content |
|---|---|
| `raw/year=YYYY/response.xml` | The response of the web service, byte for byte. |
| `parquet/year=YYYY/exchange_rates.parquet` | The same records in columnar form. |

The Parquet files keep the field names of the source and every value as text:

| Column | Example | Meaning |
|---|---|---|
| `moneda` | `2` | Currency code used by the source (2 is the US dollar). |
| `fecha` | `13/10/2026` | Date of the rate, as `dd/mm/yyyy`. |
| `venta` | `7.63381` | Selling rate. |
| `compra` | `7.63381` | Buying rate. |
| `_source_file` | `banguat/exchange_rates/raw/year=2026/response.xml` | Raw object the row was read from. |
| `_ingested_at` | `2026-10-13 23:31:08+00` | When the job that wrote the row started (UTC). |

## Silver layout

The dbt model `stg_banguat__exchange_rates` is written to
`banguat/exchange_rates/exchange_rates.parquet` in the silver bucket, as one
file with one row per published day:

| Column | Type | Meaning |
|---|---|---|
| `rate_date` | `DATE` | Calendar day the rate applies to. |
| `currency_code` | `VARCHAR` | ISO 4217 code of the currency being priced (`USD`). |
| `buy_rate` | `DECIMAL(10,6)` | Buying rate, in quetzales per unit of the currency. |
| `sell_rate` | `DECIMAL(10,6)` | Selling rate, in quetzales per unit of the currency. |
| `source_file` | `VARCHAR` | Raw object in bronze the row came from. |
| `ingested_at` | `TIMESTAMP WITH TIME ZONE` | When the ingestion run that loaded the row started. |

## Data quality

Profiling the full history (13,486 rows, 1989-11-06 to 2026-10-13) showed
three properties of the source. Silver keeps the published values as they are
and the tests encode each property, so the build fails on anything new.

| Finding | How it is handled |
|---|---|
| Five calendar days have no record: 2000-04-02, 2000-05-01, 2001-09-02, 2004-03-06 and 2004-03-07. | They are listed in the seed `banguat_known_missing_dates`. One test fails on any other missing day; another fails if a listed day appears in the data, so the list cannot go stale. |
| On 85 days between 1989-11-16 and 1991-04-09 the selling rate is below the buying rate. | Kept as published. A test requires the selling rate to be at least the buying rate from 1992 on. |
| Buying and selling rates differ on every day up to 2006-12-01 and are equal on every day since 2006-12-02. | A test requires both rates to be equal from 2006-12-02 on. If they diverge again, the meaning of the fields has changed. |

The remaining tests check that no column is null, that `rate_date` is unique,
that the currency is `USD`, that both rates fall between 1 and 20 quetzales
(the historical range is 2.78 to 8.39), and that silver has exactly as many
rows as bronze. A unit test checks the conversion from source text to typed
values on a fixed input row.

## Development

Both projects use [uv](https://docs.astral.sh/uv/).

Ingestion tests:

```bash
cd ingestion
uv run pytest
```

Running the ingestion job outside Docker against the local store:

```bash
cd ingestion
uv run --env-file ../.env python -m quetzal_ingestion.exchange_rates
```

Running dbt outside Docker (the first command downloads the dbt packages):

```bash
cd transform
uv run --env-file ../.env dbt deps
uv run --env-file ../.env dbt build
```

## Design decisions

### Storage

**Object storage behind the S3 API instead of a local folder.** A folder would
be simpler, but every reader and writer would then depend on file paths.
Talking to an S3 endpoint from the start means that moving to AWS S3 changes
configuration (endpoint and credentials), not code.

**SeaweedFS instead of MinIO.** MinIO was the original choice. When this stack
was written (October 2026) the MinIO community repository was archived and its
official images could no longer be pulled from Docker Hub, so a compose file
based on them would not start. SeaweedFS is Apache-2.0 licensed, actively
maintained, and runs as a single container. Two alternatives were rejected:
RustFS, because its first stable release was less than a month old, and a
community fork of MinIO, because it is a third-party build of code its
original authors abandoned.

**One bucket per layer.** Each layer gets its own bucket rather than a prefix
inside a shared one, so access rules and retention can differ per layer: for
example, ingestion may only write to bronze and a dashboard may only read from
gold. A bucket is created when its layer is built.

**Pinned image tag.** The image starts several components with defaults that
may change between releases. Pinning `4.48` keeps `docker compose up`
reproducible.

**Port published on loopback only.** The S3 port is bound to `127.0.0.1`, so
the store is reachable from the development machine and not from the network.

**Project-specific variable names in `.env`.** The store's key pair is read
from `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`, not from the standard
`AWS_*` names. Compose gives shell variables priority over `.env`, so reusing
the standard names could silently pass real AWS credentials from a developer's
shell into the local container.

### Ingestion

**A calendar year is the unit of work.** The job requests one whole year,
stores it under one partition with fixed object names, and replaces that
partition on every run. Because what is fetched, what is stored and what is
overwritten are the same thing, running the job twice cannot duplicate data
and needs no record of previous runs. The alternative, loading only the days
added since the last run, was rejected: it needs stored state and appends
rows, which is exactly what produces duplicates when a run is retried.

**Partitioned by the year of the rate.** The source has about one record per
day, so daily or monthly partitions would create thousands or hundreds of
files with a handful of rows each. Yearly partitions give 38 files of about
365 rows. Partitioning by ingestion date was also rejected: it keeps every
version the source ever returned, but the same rate date would appear in many
partitions and every reader would have to deduplicate.

**Raw response and Parquet copy side by side.** The XML is what the source
actually sent, so the Parquet files can be rebuilt if the parser turns out to
be wrong, without calling the source again. The Parquet copy exists because
DuckDB and dbt read it directly and do not read XML.

**Bronze stores text, not types.** Dates and numbers are kept as the source
wrote them. Converting them is a transformation that can fail, and failures
belong in the silver layer, where they are tested and visible.

**Responses are checked before anything is overwritten.** A response is
rejected if it is not valid XML, if the number of records does not match the
count the service declares, if it is empty, or if it contains dates from
another year. A rejected response leaves the stored partition untouched, so an
outage at the source cannot erase data that was already loaded.

**Retries are left to whoever runs the job.** Only connection failures are
retried in-process. Any other error stops the run with a non-zero exit code.
Since re-running is always safe, retry policy can live in the scheduler
instead of being reimplemented inside each job.

**Hand-written SOAP request.** The request is a ten-line XML template. A SOAP
library such as zeep would add a large dependency to generate the same text.

**Locked dependencies, fixed runtime.** `uv.lock` records the exact version
of every dependency. The job image installs from it using a fixed Python
minor version and a pinned uv version, so it does not depend on what is
installed on the machine that builds it.

### Transformation

**Silver is Parquet in its own bucket; DuckDB is only the engine.** dbt writes
each model to the silver bucket and DuckDB keeps nothing but a view over the
file. Storage stays separate from compute: any engine that reads Parquet can
use silver, and the DuckDB database file is disposable. Keeping the tables
inside a DuckDB file was rejected because the data would leave the object
store and only DuckDB could read it. A table format such as Iceberg was left
out for now: it would add a catalog before there is a single model to manage.

**Source anomalies are kept and documented, not fixed.** Silver changes types
and names, never values. Missing days are not filled in and odd rates are not
corrected, because a row the source never published is an invention. Each
known anomaly is declared next to a test that fails on any new one.

**Strict conversions.** Dates and numbers are converted with casts that raise
an error on unexpected input, so a format change at the source stops the
build instead of producing nulls that surface later.

**Uniqueness is tested, not enforced by deduplicating.** Bronze cannot hold
the same date twice by construction. If it ever does, a failing test is more
useful than a model that silently picks one row.

**Exact decimals for rates.** Rates are `DECIMAL(10,6)`, matching the six
decimals the source uses. Floating point would make the comparison between
buying and selling rates unreliable.

**Full rebuild on every run.** The model is rebuilt from all of bronze each
time. With 13 thousand rows an incremental model would add state and edge
cases to save a fraction of a second.

**dbt Core with dbt-duckdb, not dbt v2.** When this was written the DuckDB
adapter of the new Fusion engine was in beta and its bundled driver could not
load DuckDB extensions, including the one that reads S3.

**Layer folders, dbt model names.** Models live in folders named after the
lakehouse layers (`models/silver`). Model names follow the dbt convention for
this kind of model, `stg_<source>__<entity>`: a one-to-one cleanup of a source
table is what dbt calls a staging model.

## Known limitations

- The store runs as a single node without replication. It is a local
  development stand-in for S3, not a production deployment.
- The image also starts components this project does not use (a filer UI, an
  admin UI, an Iceberg REST catalog). Their ports are not published to the
  host.
- Only the US dollar is ingested.
- Overwriting a partition discards what it held before. If the source revises
  a past rate, the previous value is not kept.
- The two objects of a year are written one after the other, not atomically.
  A failure between them leaves the raw response newer than the Parquet file
  until the job runs again.
- The source repeats the last published rate on days without a new one, such
  as weekends. Bronze and silver keep those rows as they come.
- Silver is plain Parquet without a table format: no transactions, no schema
  evolution and no history of previous versions. The file is replaced on every
  run, after which the tests run; a failed test therefore reports a problem in
  a file that is already written.
- The freshness check is a separate command and is not part of `dbt build`.
- Nothing schedules the jobs yet; they run when someone starts them.

## Not built yet

Planned, in order:

1. Gold layer: a star schema and dbt-generated documentation.
2. Two more sources through all three layers.
3. Orchestration of the whole pipeline.
4. Governance: masking of sensitive data, lineage, and separate dev and prod
   environments.
5. A dashboard.
6. Deployment to AWS with Terraform.

Planned sources, checked for availability in October 2026:

- Guatecompras: public procurement in the Open Contracting Data Standard
  (monthly JSON files).
- Ministerio de Finanzas Públicas: budget execution (XLSX files and a CKAN
  API).

## Data sources

- Exchange rates: [Banco de Guatemala](https://www.banguat.gob.gt/), web
  service `TipoCambio`.
