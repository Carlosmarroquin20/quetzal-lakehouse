"""The failure callback, with urlopen replaced so nothing leaves the machine."""

import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import failure_alerts

CONTEXT = {
    "ti": SimpleNamespace(
        dag_id="quetzal_lakehouse",
        task_id="dbt_build",
        run_id="scheduled__2026-10-15T12:00:00+00:00",
        try_number=3,
    ),
    "exception": RuntimeError("Docker container failed: {'StatusCode': 1}"),
}


@pytest.fixture
def env(monkeypatch):
    for name in ("NOTIFICATIONS_WEBHOOK_URL", "NOTIFICATIONS_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return lambda **values: [monkeypatch.setenv(k, v) for k, v in values.items()]


class Answer:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def sent(monkeypatch) -> list[urllib.request.Request]:
    requests: list[urllib.request.Request] = []

    def urlopen(request, timeout):
        requests.append(request)
        return Answer()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


def test_the_payload_names_the_task_and_the_run():
    failed_at = datetime(2026, 10, 15, 12, 30, tzinfo=UTC)

    assert failure_alerts.failure_payload(CONTEXT, failed_at) == {
        "kind": "pipeline_failure",
        "schema_version": 1,
        "dag_id": "quetzal_lakehouse",
        "task_id": "dbt_build",
        "run_id": "scheduled__2026-10-15T12:00:00+00:00",
        "try_number": 3,
        "failed_at": "2026-10-15T12:30:00+00:00",
        "error": "RuntimeError: Docker container failed: {'StatusCode': 1}",
    }


def test_a_long_error_is_cut():
    context = {**CONTEXT, "exception": RuntimeError("x" * 2000)}

    payload = failure_alerts.failure_payload(context, datetime.now(UTC))

    assert len(payload["error"]) == failure_alerts.ERROR_LENGTH


def test_a_failure_without_an_exception():
    context = {"ti": CONTEXT["ti"]}

    assert failure_alerts.failure_payload(context, datetime.now(UTC))["error"] is None


def test_the_failure_is_posted_with_the_shared_secret(env, sent):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook/", NOTIFICATIONS_WEBHOOK_SECRET="s")

    failure_alerts.report_failure(CONTEXT)

    (request,) = sent
    assert request.get_method() == "POST"
    assert request.full_url == "http://n8n:5678/webhook/pipeline-failure"
    assert request.get_header("X-webhook-secret") == "s"
    assert request.get_header("Content-type") == "application/json"
    body = json.loads(request.data)
    assert body["task_id"] == "dbt_build"
    assert body["run_id"] == CONTEXT["ti"].run_id


def test_without_a_url_nothing_is_sent(env, sent):
    failure_alerts.report_failure(CONTEXT)

    assert sent == []


def test_without_a_secret_nothing_is_sent(env, sent, caplog):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook")

    with caplog.at_level(logging.WARNING):
        failure_alerts.report_failure(CONTEXT)

    assert sent == []
    assert "NOTIFICATIONS_WEBHOOK_SECRET" in caplog.text


def test_an_unreachable_n8n_is_logged_not_raised(env, monkeypatch, caplog):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook", NOTIFICATIONS_WEBHOOK_SECRET="s")

    def urlopen(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    with caplog.at_level(logging.WARNING):
        failure_alerts.report_failure(CONTEXT)

    assert "could not report the failure" in caplog.text
