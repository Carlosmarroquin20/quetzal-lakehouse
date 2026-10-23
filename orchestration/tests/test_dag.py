"""The DAG as Airflow loads it: structure, schedule and how tasks reach Docker.

These tests need Airflow and its Docker provider, so they run inside the same
apache/airflow image the stack uses (see docs/getting-started.md). Where
Airflow is not installed, such as the uv environment of this folder, they are
skipped.
"""

from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("airflow")
pytest.importorskip("airflow.providers.docker")

from airflow.providers.docker.operators.docker import DockerOperator  # noqa: E402

DAGS = Path(__file__).resolve().parents[1] / "dags"

# Distinct values for every secret the DAG reads, to check where each lands.
SECRETS = {
    "S3_INGESTION_ACCESS_KEY_ID": "test-ingestion-key",
    "S3_INGESTION_SECRET_ACCESS_KEY": "test-ingestion-secret",
    "S3_TRANSFORM_PROD_ACCESS_KEY_ID": "test-transform-key",
    "S3_TRANSFORM_PROD_SECRET_ACCESS_KEY": "test-transform-secret",
    "PSEUDONYMIZATION_KEY_PROD": "test-pseudonymization-key",
    "S3_NOTIFICATIONS_ACCESS_KEY_ID": "test-notifications-key",
    "S3_NOTIFICATIONS_SECRET_ACCESS_KEY": "test-notifications-secret",
    "NOTIFICATIONS_WEBHOOK_SECRET": "test-webhook-secret",
}


@pytest.fixture(scope="module")
def dag():
    with pytest.MonkeyPatch.context() as env:
        for name, value in {
            **SECRETS,
            "S3_REGION": "us-east-1",
            "S3_BUCKET_BRONZE": "quetzal-bronze",
            "S3_BUCKET_SILVER": "quetzal-silver",
            "S3_BUCKET_GOLD": "quetzal-gold",
            "PROJECT_HOST_DIR": "/host/quetzal-lakehouse",
        }.items():
            env.setenv(name, value)
        try:
            from airflow.dag_processing.dagbag import DagBag
        except ImportError:
            from airflow.models.dagbag import DagBag
        bag = DagBag(dag_folder=str(DAGS))
        assert bag.import_errors == {}
        yield bag.dags["quetzal_lakehouse"]


def test_the_tasks_run_in_order(dag):
    ingestion = {
        "ingest_exchange_rates",
        "ingest_contracting_processes",
        "ingest_budget_execution",
    }
    assert set(dag.task_ids) == ingestion | {
        "dbt_build",
        "send_daily_digest",
        "check_source_freshness",
    }
    assert dag.get_task("dbt_build").upstream_task_ids == ingestion
    assert dag.get_task("check_source_freshness").upstream_task_ids == ingestion
    assert dag.get_task("send_daily_digest").upstream_task_ids == {"dbt_build"}
    for task_id in ingestion:
        assert dag.get_task(task_id).upstream_task_ids == set()


def test_it_runs_once_a_day_without_catching_up(dag):
    assert dag.schedule == "0 6 * * *"
    assert dag.timezone.name == "America/Guatemala"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_every_task_retries_and_reports_its_final_failure(dag):
    from failure_alerts import report_failure

    for task in dag.tasks:
        if task.task_id == "check_source_freshness":
            # A stale source is not fixed by trying again.
            assert task.retries == 0
        else:
            assert task.retries == 2, task.task_id
            assert task.retry_delay == timedelta(minutes=10), task.task_id
        callbacks = task.on_failure_callback
        callbacks = callbacks if isinstance(callbacks, list) else [callbacks]
        assert report_failure in callbacks, task.task_id


def test_tasks_reach_docker_only_through_the_proxy(dag):
    for task in dag.tasks:
        assert isinstance(task, DockerOperator), task.task_id
        assert type(task).__name__ == "JobOperator", task.task_id
        assert task.docker_url == "tcp://docker-proxy:2375", task.task_id
        assert task.network_mode == "quetzal-lakehouse_default", task.task_id
        assert task.mount_tmp_dir is False, task.task_id
        assert task.auto_remove == "force", task.task_id
        assert task.labels == {"quetzal-lakehouse.task": task.task_id}


def test_secrets_never_go_through_the_rendered_environment(dag):
    # environment is shown in the Airflow interface; private_environment is not.
    for task in dag.tasks:
        shown = " ".join(str(value) for value in task.environment.values())
        for secret in SECRETS.values():
            assert secret not in shown, task.task_id
    # The operator keeps private_environment in an attribute of its own.
    assert set(dag.get_task("dbt_build")._private_environment.values()) == {
        SECRETS["S3_TRANSFORM_PROD_ACCESS_KEY_ID"],
        SECRETS["S3_TRANSFORM_PROD_SECRET_ACCESS_KEY"],
        SECRETS["PSEUDONYMIZATION_KEY_PROD"],
    }


def test_dbt_runs_the_prod_environment(dag):
    assert dag.get_task("dbt_build").environment["DBT_TARGET"] == "prod"


def test_the_digest_is_skipped_when_no_webhook_is_set(dag):
    digest = dag.get_task("send_daily_digest")
    skip = digest.skip_on_exit_code
    assert 3 in (skip if isinstance(skip, (list, set, tuple)) else [skip])


def test_freshness_uses_a_duckdb_file_of_its_own(dag):
    # dbt_build keeps its DuckDB file in a volume; two processes cannot open
    # one file at once, and the two tasks run side by side.
    freshness = dag.get_task("check_source_freshness")
    assert freshness.command == ["source", "freshness"]
    assert freshness.environment["DBT_DUCKDB_PATH"] == "/tmp/freshness.duckdb"
    assert freshness.mounts == []
    assert freshness.environment["DBT_TARGET"] == "prod"


def test_a_killed_task_removes_its_container_at_once(dag):
    # No graceful stop to wait for: one forced removal, which kills it.
    from unittest import mock

    task = dag.get_task("dbt_build")
    client = mock.Mock()
    with mock.patch.object(type(task), "hook", mock.PropertyMock()) as hook, \
            mock.patch.object(type(task), "cli", mock.PropertyMock(return_value=client)):
        hook.return_value.client_created = True
        task.container = {"Id": "abc123"}
        task.on_kill()
    client.remove_container.assert_called_once_with("abc123", force=True)
    client.stop.assert_not_called()

