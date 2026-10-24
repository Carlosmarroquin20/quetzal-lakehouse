# Getting started

[Back to the README](../README.md)

Requirements: Docker with Compose v2, and about 2 GB of disk for the data.

1. Create your local configuration and replace the placeholder values:

   ```bash
   cp .env.example .env
   ```

2. Start the object store and wait until it is healthy:

   ```bash
   docker compose up -d --wait
   ```

3. Load the full exchange rate history into bronze (about ten seconds; the
   first run also builds the job image):

   ```bash
   docker compose run --rm ingestion exchange-rates --from-year 1989
   ```

4. Load the contracting processes published since January 2025 (22 files and
   about 0.7 GB in October 2026; six to seven minutes):

   ```bash
   docker compose run --rm ingestion contracting-processes --from-month 2025-01
   ```

5. Download the budget execution workbooks from the
   [MINFIN open data portal](https://datos.minfin.gob.gt) in a browser: the
   resource "Ejecución Presupuesto de Egresos de Gobierno Central" of the
   datasets "Ejecución Presupuestaria 2025" and "Ejecución Presupuestaria
   2026". Put them in `landing/minfin/`, with any file name, and load them
   (about a minute):

   ```bash
   docker compose run --rm ingestion budget-execution
   ```

6. Build the silver and gold layers of the prod environment and run their
   tests (about four minutes):

   ```bash
   docker compose run --rm transform
   ```

   This runs `dbt build`: silver, and gold in `gold.staging`, with every
   test. It should end with `PASS=225 ... ERROR=0`. Then publish gold, which
   is what the dashboard and the digest read:

   ```bash
   docker compose run --rm transform run-operation publish_gold
   ```

   Publishing refuses unless the last build passed; Airflow does both steps
   on its own. To try a change without touching prod, run the same build in
   dev, which writes its own silver and gold buckets and catalogs:

   ```bash
   docker compose run --rm transform-dev
   ```

7. Open the documentation of the models, with their lineage graph, at
   <http://localhost:8080>:

   ```bash
   docker compose up -d docs
   ```

   The site describes what the last transform run built, and takes about
   half a minute to come up.

8. Open the dashboard at <http://localhost:8501> (the first start builds its
   image):

   ```bash
   docker compose up -d dashboard
   ```

   It reads prod gold, so it shows what the last prod transform run built.

Without a range, the two jobs that download refresh the current period
only: the current year of exchange rates, or the current month of
contracting processes. The budget job loads whatever workbooks are in the
landing folder; to refresh the current year, download its workbook again and
replace the old file.

```bash
docker compose run --rm ingestion exchange-rates
docker compose run --rm ingestion contracting-processes
```

Running any of these commands again replaces the same objects. Nothing is
duplicated. The contracting processes job does not even download a month
again while the source has not changed it, and the budget job does not write
a workbook bronze already holds.

## Running it every day with Airflow

Airflow starts the same images on a schedule. It needs the Airflow values of
`.env` (see `.env.example`), including `PROJECT_HOST_DIR`, the absolute path
of this repository, from which its tasks mount `landing/`.

1. Build the job images, which Airflow starts by name:

   ```bash
   docker compose build ingestion transform notifications
   ```

2. Start Airflow (about two minutes the first time):

   ```bash
   docker compose --profile airflow up -d --wait
   ```

3. Open <http://localhost:8081>. The DAG `quetzal_lakehouse` is active and
   runs every day at 06:00, Guatemala time; the button to trigger it runs it
   now. A full run takes about twelve minutes.

## Notifications with n8n

n8n runs in its own profile and needs `N8N_ENCRYPTION_KEY` in `.env` (see
`.env.example`).

1. Start it and wait until it is healthy:

   ```bash
   docker compose --profile notifications up -d --wait
   ```

2. Open <http://localhost:5678>. The first time, n8n asks for an owner
   account; it is stored only in n8n's volume on this machine.

The credentials to create, the import of the workflows and how to try them
with a sample payload are in [Notifications](notifications.md).

## Checking and stopping the stack

Airflow checks every day how old the bronze data is, and its failure alert
says when a source is past its limit: seven days for the exchange rate and
Guatecompras, 35 days for the budget workbook. To check by hand:

```bash
docker compose run --rm transform source freshness
```

The S3 endpoint is `http://localhost:8333`. Requests must be signed with the
key pair from `.env`; unsigned requests and wrong keys are rejected.

To stop the stack, including the documentation site, the dashboard, Airflow
and n8n, and keep the data:

```bash
docker compose --profile docs --profile dashboard --profile airflow --profile notifications down
```

Adding `-v` also deletes the volumes, and with them every stored object and
everything n8n stored.

Every container Airflow starts carries the label `quetzal-lakehouse.task`
with the name of its task, and is removed when the task ends or is killed.
If the scheduler itself dies first, a stopped container can stay behind. To
list and remove those:

```bash
docker ps --all --filter label=quetzal-lakehouse.task
docker container prune --filter label=quetzal-lakehouse.task
```

## Development

The Python projects use [uv](https://docs.astral.sh/uv/).

Tests of the ingestion jobs, the dashboard, the digest and the DAG's failure
callback, none of which needs the network:

```bash
cd ingestion
uv run pytest
cd ../dashboard
uv run pytest
cd ../notifications
uv run pytest
cd ../orchestration
uv run pytest
```

The tests of the DAG itself need Airflow, so the uv environment skips them.
They run inside the Airflow image the stack uses:

```bash
docker run --rm -v "$PWD/orchestration:/opt/orchestration:ro" -w /opt/orchestration --entrypoint bash apache/airflow:3.3.2 -c "pip install -q pytest==9.1.1 && python -m pytest -p no:cacheprovider tests"
```

Jobs run through Compose, which hands each one the key pair of its role:
`docker compose run --rm ingestion <job>` for ingestion, and
`docker compose run --rm transform-dev` for dbt while developing. Any dbt
command can follow the service name, for example
`docker compose run --rm transform-dev test --select dim_supplier`. The
dashboard runs from its image too, so a change to it needs
`docker compose up -d --build dashboard`.

A separate workflow (`.github/workflows/docs.yml`) publishes the dbt
documentation to GitHub Pages, at <https://carlosmarroquin20.github.io/quetzal-lakehouse/>, on every push to main
that changes the dbt project.

GitHub Actions runs the same tests on every push and pull request
(`.github/workflows/ci.yml`), together with `dbt parse` and every dbt unit
test, the DAG loaded in the Airflow image, `terraform fmt` and `validate`, a
check of the Compose file against `.env.example`, `pip-audit` on each lock
file, a Trivy scan of the four project images, and gitleaks on the whole
history. None of it needs a store or a credential. Dependabot
(`.github/dependabot.yml`) opens weekly pull requests for the Python
packages, the images, the Terraform provider and the actions.
