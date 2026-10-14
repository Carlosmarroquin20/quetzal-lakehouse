"""Daily run of the whole lakehouse pipeline.

Airflow only schedules. Each task starts one of the project's images as a
container, the same way `docker compose run` does: the three ingestion jobs
land their sources in bronze, and once all of them succeed, dbt rebuilds
silver and gold and runs the tests.

Every job is idempotent, so a failed task can simply run again. That is why
retries live here and not inside the jobs.
"""

import os
from datetime import timedelta

import pendulum
from docker.types import Mount

from airflow.providers.docker.operators.docker import DockerOperator
from airflow.sdk import DAG

NETWORK = "quetzal-lakehouse_default"
INGESTION_IMAGE = "quetzal-lakehouse-ingestion"
TRANSFORM_IMAGE = "quetzal-lakehouse-transform"

# Configuration the containers need. The key pair goes through
# private_environment, which Airflow neither renders in its interface nor
# writes to the logs.
STORAGE = {
    "S3_ENDPOINT_URL": "http://storage:8333",
    "S3_REGION": os.environ.get("S3_REGION", ""),
    "S3_BUCKET_BRONZE": os.environ.get("S3_BUCKET_BRONZE", ""),
    "S3_BUCKET_SILVER": os.environ.get("S3_BUCKET_SILVER", ""),
    "S3_BUCKET_GOLD": os.environ.get("S3_BUCKET_GOLD", ""),
}
CREDENTIALS = {
    "S3_ACCESS_KEY_ID": os.environ.get("S3_ACCESS_KEY_ID", ""),
    "S3_SECRET_ACCESS_KEY": os.environ.get("S3_SECRET_ACCESS_KEY", ""),
}

# Guatecompras is loaded from this month on. Months the source has not changed
# are skipped by their checksum, so the whole range costs little to refresh.
GUATECOMPRAS_FIRST_MONTH = "2025-01"


def job(task_id: str, image: str, command: list[str], mounts: list[Mount] | None = None) -> DockerOperator:
    return DockerOperator(
        task_id=task_id,
        image=image,
        command=command,
        environment=STORAGE,
        private_environment=CREDENTIALS,
        network_mode=NETWORK,
        mounts=mounts or [],
        # The operator would otherwise try to mount a temporary folder of the
        # Airflow container, which the Docker daemon cannot see.
        mount_tmp_dir=False,
        auto_remove="force",
        docker_url="unix://var/run/docker.sock",
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
    },
    tags=["lakehouse"],
) as dag:
    exchange_rates = job("ingest_exchange_rates", INGESTION_IMAGE, ["exchange-rates"])

    contracting_processes = job(
        "ingest_contracting_processes",
        INGESTION_IMAGE,
        ["contracting-processes", "--from-month", GUATECOMPRAS_FIRST_MONTH],
    )

    budget_execution = job(
        "ingest_budget_execution",
        INGESTION_IMAGE,
        ["budget-execution"],
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
        mounts=[
            Mount(source="quetzal-lakehouse_transform-state", target="/app/state", type="volume")
        ],
    )

    [exchange_rates, contracting_processes, budget_execution] >> dbt_build
