"""Posting the digest to n8n, with a fake transport instead of the network."""

import json

import httpx
import pytest

from quetzal_notifications import __main__ as cli
from quetzal_notifications import gold, webhook

SETTINGS = webhook.WebhookSettings(base_url="http://n8n:5678/webhook", secret="shared-secret")


@pytest.fixture
def env(monkeypatch):
    for name in ("NOTIFICATIONS_WEBHOOK_URL", "NOTIFICATIONS_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return lambda **values: [monkeypatch.setenv(k, v) for k, v in values.items()]


@pytest.fixture
def received(monkeypatch) -> list[httpx.Request]:
    """Requests the job sends, answered the way n8n answers a webhook."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": "Workflow was started"})

    monkeypatch.setattr(
        webhook, "create_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return requests


def test_the_payload_is_posted_with_the_shared_secret():
    requests = []
    transport = httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200))

    with httpx.Client(transport=transport) as client:
        webhook.post(client, SETTINGS, "daily-digest", {"kind": "daily_digest"})

    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "http://n8n:5678/webhook/daily-digest"
    assert request.headers[webhook.SECRET_HEADER] == "shared-secret"
    assert json.loads(request.content) == {"kind": "daily_digest"}


def test_a_refused_request_fails():
    transport = httpx.MockTransport(lambda r: httpx.Response(403))

    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        webhook.post(client, SETTINGS, "daily-digest", {})


def test_settings_come_from_the_environment(env):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook/", NOTIFICATIONS_WEBHOOK_SECRET="s")

    settings = webhook.WebhookSettings.from_env()

    assert settings.url("daily-digest") == "http://n8n:5678/webhook/daily-digest"


def test_without_a_url_notifications_are_off(env):
    with pytest.raises(webhook.NotConfigured):
        webhook.WebhookSettings.from_env()


def test_a_url_without_a_secret_is_rejected(env):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook")

    with pytest.raises(RuntimeError, match="SECRET"):
        webhook.WebhookSettings.from_env()


def test_posting_without_a_url_ends_before_reading_gold(env, monkeypatch, received):
    monkeypatch.setattr(gold, "connect", lambda: pytest.fail("gold was read"))

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["digest", "--post"])

    assert exit_info.value.code == cli.NOT_CONFIGURED
    assert received == []


def test_the_job_posts_the_digest_it_prints(env, monkeypatch, received, con, capsys):
    env(NOTIFICATIONS_WEBHOOK_URL="http://n8n:5678/webhook", NOTIFICATIONS_WEBHOOK_SECRET="s")
    monkeypatch.setattr(gold, "connect", lambda: con)

    cli.main(["digest", "--post", "--run-date", "2026-10-15", "--run-id", "run-1"])

    (request,) = received
    posted = json.loads(request.content)
    assert posted == json.loads(capsys.readouterr().out)
    assert posted["kind"] == "daily_digest"
    assert posted["run_id"] == "run-1"
    assert posted["awards"]["date"] == "2026-10-14"


def test_without_post_nothing_is_sent(env, monkeypatch, received, con):
    monkeypatch.setattr(gold, "connect", lambda: con)

    cli.main(["digest", "--run-date", "2026-10-15"])

    assert received == []
