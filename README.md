# quetzal-lakehouse

[![CI](https://github.com/Carlosmarroquin20/quetzal-lakehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/Carlosmarroquin20/quetzal-lakehouse/actions/workflows/ci.yml)

A lakehouse on public financial data from Guatemala: the central bank's
exchange rate, public procurement and the central government's budget. Each
source lands untouched in bronze, dbt and DuckDB turn it into typed silver
tables and a star schema in gold, Airflow runs it every day, and a dashboard
reads gold. Each run ends with a digest sent to Telegram and by email through
a self-hosted n8n, which also reports failures. Terraform describes the AWS
storage and roles it would run on, tested against a local AWS emulator.

Everything described here exists in the repository. Planned work is listed
under [Status](#status).

![The awards page of the dashboard, showing the valid awards of 2026 per month](docs/images/dashboard-awards.png)

*The awards page of the dashboard, with the data loaded on 2026-10-14.*

## What it answers

- How much the government awards each year, under which procedures and to
  whom, in quetzales and in dollars at the exchange rate of each day.
- How much of its budget each central government entity has spent, next to
  what it awarded through public procurement.
- How the quetzal has moved against the dollar since 1989.

## Highlights

- **Three sources, three shapes:** a SOAP/XML web service, about 0.7 GB of
  zipped JSON in the Open Contracting Data Standard on every refresh, and
  Excel workbooks behind a bot challenge, which are downloaded by hand rather
  than worked around.
- **Idempotent ingestion:** each job replaces whole periods (a year, a month)
  under fixed names, so a rerun never duplicates data, and months the source
  has not changed are skipped by their checksum.
- **Storage apart from compute:** every layer is Parquet in its own bucket of
  an S3-compatible store; DuckDB is only the engine, so moving to AWS S3
  changes configuration, not code. That was checked by running the jobs
  against an AWS emulator with the temporary credentials of their IAM roles.
- **A dimensional model:** three fact tables (513,471 awards, 329,256 budget
  lines, a daily exchange rate) sharing date, currency and entity dimensions,
  so budget and procurement can be compared entity by entity.
- **Tests that encode what profiling found:** 195 dbt data tests and 8 unit
  tests fail on new anomalies, not on the known ones; 71 ingestion tests, 16
  dashboard tests, 22 digest tests and 7 tests of the DAG's failure callback
  cover the Python code.
- **Continuous integration:** every push runs those tests, checks the dbt
  project, the Terraform configuration and the Compose file, audits the
  locked dependencies for known vulnerabilities and scans the history for
  secrets. Dependabot proposes updates every week.
- **Governance:** natural persons are pseudonymized in gold with a keyed hash,
  each job has a storage key pair that reaches only its own buckets, dbt runs
  in separate dev and prod environments, and the lineage runs from each source
  to the dashboard.
- **Runs on its own:** Airflow runs the whole pipeline every day at 06:00,
  Guatemala time.
- **Notifications:** each run ends with a digest of gold (the dollar rate and
  its change, the awards of the day before, the largest of them) sent to
  Telegram and by email, with alerts above configurable thresholds; a task
  that fails for good is reported at once. Airflow computes and posts, n8n
  only words and routes the messages, behind a shared secret, and the
  workflows are versioned in the repository.
- **Infrastructure as code:** Terraform creates the AWS buckets, with
  encryption, blocked public access and versioned bronze, and one
  least-privilege IAM role per job. It has never been applied to an AWS
  account, so it has cost nothing.

Row counts are from the run of 2026-10-13.

## Architecture

```mermaid
flowchart LR
    banguat["Banco de Guatemala<br/>exchange rates<br/>(SOAP/XML)"]
    guatecompras["Guatecompras<br/>contracting processes<br/>(zipped JSON, OCDS)"]
    minfin["MINFIN<br/>budget execution<br/>(XLSX)"]
    landing[/"landing/minfin/<br/>downloaded by hand"/]
    subgraph compose["Docker Compose"]
        airflow["Airflow<br/>daily at 06:00<br/>127.0.0.1:8081"]
        ingestion["ingestion jobs<br/>(Python)"]
        transform["transform job<br/>(dbt + DuckDB)"]
        docs["docs<br/>dbt documentation site<br/>127.0.0.1:8080"]
        dashboard["dashboard<br/>(Streamlit + DuckDB)<br/>127.0.0.1:8501"]
        notifications["notifications job<br/>(daily digest)"]
        n8n["n8n<br/>127.0.0.1:5678"]
        subgraph storage["storage: SeaweedFS S3 gateway, 127.0.0.1:8333"]
            bronze[("quetzal-bronze<br/>original files + Parquet<br/>partitioned by period")]
            silver[("quetzal-silver<br/>typed Parquet")]
            gold[("quetzal-gold<br/>dimensional model in Parquet")]
        end
    end
    banguat -- "one request per year" --> ingestion
    guatecompras -- "one file per month" --> ingestion
    minfin -- "browser download" --> landing
    landing -- "one workbook per year" --> ingestion
    ingestion -- "write" --> bronze
    bronze -- "read" --> transform
    transform -- "write, then test" --> silver
    transform -- "write, then test" --> gold
    transform -. "models, tests and lineage" .-> docs
    gold -- "read only" --> dashboard
    gold -- "read only" --> notifications
    airflow -. "starts" .-> ingestion
    airflow -. "starts, after ingestion" .-> transform
    airflow -. "starts, after dbt" .-> notifications
    notifications -- "digest" --> n8n
    airflow -- "failed task" --> n8n
    n8n -- "messages" --> channels["Telegram<br/>and email"]
```

## Stack

| Part | Tools |
|---|---|
| Object storage | SeaweedFS behind the S3 API |
| Ingestion | Python 3.13, httpx, pyarrow, uv |
| Transformation | dbt Core 1.12 with dbt-duckdb, DuckDB 1.5 |
| Orchestration | Airflow 3.3 with the local executor and Postgres |
| Dashboard | Streamlit with DuckDB |
| Notifications | n8n 2.43 Community Edition, Telegram, SMTP |
| Infrastructure | Terraform 1.16 with the AWS provider; Moto as the AWS emulator |
| Runtime | Docker Compose |

## Repository layout

| Path | What it holds |
|---|---|
| `ingestion/` | The jobs that land each source in bronze, as one Python package with its tests. |
| `transform/` | The dbt project: silver and gold models, tests, seeds and the pseudonymization plugin. |
| `orchestration/` | The Airflow DAG and its failure callback, with the callback's tests. |
| `dashboard/` | The Streamlit dashboard, its queries and their tests. |
| `notifications/` | The job that computes the daily digest from gold and posts it, with its tests. |
| `automation/n8n/` | The n8n workflows, the script that imports them, sample payloads and the script that normalizes an export. |
| `infra/aws/` | The Terraform configuration of the AWS storage and roles. |
| `docs/` | The documentation listed below. |
| `docker-compose.yml` | Every service and job, with the storage roles. |
| `.env.example` | The configuration to copy into a local `.env`, which git ignores. |

## Quick start

Requirements: Docker with Compose v2, and about 2 GB of disk. A first full
load takes about fifteen minutes.

```bash
cp .env.example .env                    # then replace the placeholder values
docker compose up -d --wait             # object store
docker compose run --rm ingestion exchange-rates --from-year 1989
docker compose run --rm ingestion contracting-processes --from-month 2025-01
docker compose run --rm ingestion budget-execution    # workbooks in landing/minfin/
docker compose run --rm transform       # dbt build: silver, gold and tests
docker compose up -d dashboard          # http://localhost:8501
```

The budget workbooks have to be downloaded by hand first;
[Getting started](docs/getting-started.md) says where from, and covers the
documentation site, Airflow and development.

## Documentation

| Document | What it covers |
|---|---|
| [dbt documentation](https://carlosmarroquin20.github.io/quetzal-lakehouse/) | Every model, column, test and source, and the lineage graph from the sources to the dashboard, published from main. |
| [Getting started](docs/getting-started.md) | Every step to run the project, the dbt documentation site, Airflow, and development. |
| [Data model](docs/data-model.md) | The bronze, silver and gold layouts, the star schema with example queries, and the dashboard. |
| [Data quality](docs/data-quality.md) | What profiling each source found, and the tests that encode it. |
| [Governance](docs/governance.md) | Personal data and its masking, the storage roles, the two environments, and lineage. |
| [Design decisions](docs/design-decisions.md) | Each decision, with the alternatives that were rejected. |
| [Notifications](docs/notifications.md) | The daily digest and failure alerts: how they travel, the payloads, the settings and credentials, and how to try and change the workflows. |
| [AWS](docs/aws.md) | The Terraform configuration, how to try it against the emulator, and what a deployment would add. |
| [Known limitations](docs/known-limitations.md) | What the project does not handle, or handles only in part. |

## Status

Built, in this order: the choice of sources, the storage, the bronze, silver
and gold layers for the exchange rate, procurement and the budget, the daily
orchestration, governance, the dashboard, the Terraform configuration of the
AWS storage and roles, and the notifications.

Not built: an actual AWS deployment (container images, scheduled tasks, the
dashboard behind a login), which would cost money to run; see
[AWS](docs/aws.md#what-a-deployment-would-add). Nor a table format for
silver and gold.

## Data sources

- Exchange rates: [Banco de Guatemala](https://www.banguat.gob.gt/), web
  service `TipoCambio`.
- Contracting processes: [Guatecompras](https://ocds.guatecompras.gt/),
  Ministerio de Finanzas Públicas, published in the Open Contracting Data
  Standard under the
  [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
  license.
- Budget execution: [Ministerio de Finanzas Públicas](https://datos.minfin.gob.gt/),
  datasets "Ejecución Presupuestaria". The 2025 dataset is published under the
  Creative Commons Attribution license; the 2026 dataset does not state a
  license yet.
