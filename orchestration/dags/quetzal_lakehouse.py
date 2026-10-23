"""Daily run of the whole lakehouse pipeline.

Airflow only schedules. Each task starts one of the project's images as a
container, the same way `docker compose run` does: the three ingestion jobs
land their sources in bronze, and once all of them succeed, dbt rebuilds
silver and gold and runs the tests. The last task posts a digest of the new
gold to n8n, which words it and sends it on.

Every job is idempotent, so a failed task can simply run again. That is why
retries live here and not inside the jobs. A task that still fails after its
retries is reported to n8n, which sends the alert.
"""

import os
from datetime import timedelta

import pendulum
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.sdk import DAG
from docker.types import Mount

from failure_alerts import report_failure

NETWORK = "quetzal-lakehouse_default"
INGESTION_IMAGE = "quetzal-lakehouse-ingestion"
TRANSFORM_IMAGE = "quetzal-lakehouse-transform"
NOTIFICATIONS_IMAGE = "quetzal-lakehouse-notifications"

# Configuration the containers need. Airflow runs the prod environment.
STORAGE = {
    "S3_ENDPOINT_URL": "http://storage:8333",
    "S3_REGION": os.environ.get("S3_REGION", ""),
    "S3_BUCKET_BRONZE": os.environ.get("S3_BUCKET_BRONZE", ""),
    "S3_BUCKET_SILVER": os.environ.get("S3_BUCKET_SILVER", ""),
    "S3_BUCKET_GOLD": os.environ.get("S3_BUCKET_GOLD", ""),
    "DBT_TARGET": "prod",
}

# Each kind of task gets the key pair of its own role: ingestion can only
# write bronze, prod dbt can only write prod silver and gold. Secrets go
# through private_environment, which Airflow neither renders in its
# interface nor writes to the logs.
INGESTION_SECRETS = {
    "S3_ACCESS_KEY_ID": os.environ.get("S3_INGESTION_ACCESS_KEY_ID", ""),
    "S3_SECRET_ACCESS_KEY": os.environ.get("S3_INGESTION_SECRET_ACCESS_KEY", ""),
}
TRANSFORM_SECRETS = {
    "S3_ACCESS_KEY_ID": os.environ.get("S3_TRANSFORM_PROD_ACCESS_KEY_ID", ""),
    "S3_SECRET_ACCESS_KEY": os.environ.get("S3_TRANSFORM_PROD_SECRET_ACCESS_KEY", ""),
    "PSEUDONYMIZATION_KEY": os.environ.get("PSEUDONYMIZATION_KEY_PROD", ""),
}
# The digest reads prod gold with a key pair that can do nothing else, and
# proves itself to n8n with the secret the webhooks check.
NOTIFICATIONS_SECRETS = {
    "S3_ACCESS_KEY_ID": os.environ.get("S3_NOTIFICATIONS_ACCESS_KEY_ID", ""),
    "S3_SECRET_ACCESS_KEY": os.environ.get("S3_NOTIFICATIONS_SECRET_ACCESS_KEY", ""),
    "NOTIFICATIONS_WEBHOOK_SECRET": os.environ.get("NOTIFICATIONS_WEBHOOK_SECRET", ""),
}
NOTIFICATIONS = {
    "NOTIFICATIONS_WEBHOOK_URL": os.environ.get("NOTIFICATIONS_WEBHOOK_URL", ""),
}
# What the digest job exits with when no webhook URL is set: the task is then
# skipped instead of failed, so the pipeline runs the same without n8n.
DIGEST_NOT_CONFIGURED = 3

# Every container a task starts carries this label. When Airflow kills a
# task, the operator removes its container; if the scheduler itself dies
# first, the leftovers can be found by the label (docs/getting-started.md).
JOB_LABEL = "quetzal-lakehouse.task"

# Guatecompras is loaded from this month on. Months the source has not changed
# are skipped by their checksum, so the whole range costs little to refresh.
GUATECOMPRAS_FIRST_MONTH = "2025-01"


def job(
    task_id: str,
    image: str,
    command: list[str],
    secrets: dict[str, str],
    mounts: list[Mount] | None = None,
    environment: dict[str, str] | None = None,
    skip_on_exit_code: int | None = None,
    retries: int | None = None,
) -> DockerOperator:
    # None keeps the retries of default_args.
    extra = {} if retries is None else {"retries": retries}
    return DockerOperator(
        **extra,
        task_id=task_id,
        image=image,
        command=command,
        environment={**STORAGE, **(environment or {})},
        private_environment=secrets,
        skip_on_exit_code=skip_on_exit_code,
        network_mode=NETWORK,
        mounts=mounts or [],
        # The operator would otherwise try to mount a temporary folder of the
        # Airflow container, which the Docker daemon cannot see.
        mount_tmp_dir=False,
        auto_remove="force",
        labels={JOB_LABEL: task_id},
        # Docker is reached through the socket proxy, never the socket itself.
        docker_url="tcp://docker-proxy:2375",
    )


with DAG(
    dag_id="quetzal_lakehouse",
    description="Land the three sources in bronze, then build silver and gold with dbt.",
    doc_md=__doc__,
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Guatemala"),
    # A missed day is not run later: each run already refreshes everything.
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
        # Called once a task has failed for good, not on each retry.
        "on_failure_callback": report_failure,
    },
    tags=["lakehouse"],
) as dag:
    exchange_rates = job(
        "ingest_exchange_rates", INGESTION_IMAGE, ["exchange-rates"], INGESTION_SECRETS
    )

    contracting_processes = job(
        "ingest_contracting_processes",
        INGESTION_IMAGE,
        ["contracting-processes", "--from-month", GUATECOMPRAS_FIRST_MONTH],
        INGESTION_SECRETS,
    )

    budget_execution = job(
        "ingest_budget_execution",
        INGESTION_IMAGE,
        ["budget-execution"],
        INGESTION_SECRETS,
        mounts=[
            Mount(
                source=f"{os.environ.get('PROJECT_HOST_DIR', '')}/landing",
                target="/landing",
                type="bind",
                read_only=True,
            )
        ],
    )

    dbt_build = job(
        "dbt_build",
        TRANSFORM_IMAGE,
        ["build"],
        TRANSFORM_SECRETS,
        mounts=[
            Mount(
                source="quetzal-lakehouse_transform-state",
                target="/app/state",
                type="volume",
            )
        ],
    )

    # Fails when a source has gone longer without a new load than its error
    # threshold allows, and the failure alert says so. It runs beside dbt, so
    # stale data is reported without holding back the build, on a DuckDB file
    # of its own so the two never compete for one. Retrying would not make a
    # source any fresher.
    source_freshness = job(
        "check_source_freshness",
        TRANSFORM_IMAGE,
        ["source", "freshness"],
        TRANSFORM_SECRETS,
        environment={"DBT_DUCKDB_PATH": "/tmp/freshness.duckdb"},
        retries=0,
    )

    # The day the digest reports on is the day of the run in Guatemala,
    # which the job works out itself; the run ID lets a message be traced
    # back to its run.
    daily_digest = job(
        "send_daily_digest",
        NOTIFICATIONS_IMAGE,
        ["digest", "--post", "--run-id", "{{ run_id }}"],
        NOTIFICATIONS_SECRETS,
        environment=NOTIFICATIONS,
        skip_on_exit_code=DIGEST_NOT_CONFIGURED,
    )

    ingestion = [exchange_rates, contracting_processes, budget_execution]
    ingestion >> dbt_build >> daily_digest
    ingestion >> source_freshness
