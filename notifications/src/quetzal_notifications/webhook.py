"""Posting to n8n's webhooks.

n8n listens under one base URL, with a fixed path per kind of notification.
Each request carries a secret shared with n8n in a header, which n8n checks
before running the workflow, so only the pipeline can trigger a message.
"""

import os
from dataclasses import dataclass

import httpx

# Has to match the header n8n's webhooks check.
SECRET_HEADER = "X-Webhook-Secret"
DIGEST_PATH = "daily-digest"


class NotConfigured(Exception):
    """No webhook URL is set, so notifications are turned off."""


@dataclass(frozen=True)
class WebhookSettings:
    base_url: str
    secret: str

    @classmethod
    def from_env(cls) -> "WebhookSettings":
        base_url = os.environ.get("NOTIFICATIONS_WEBHOOK_URL", "")
        if not base_url:
            raise NotConfigured("NOTIFICATIONS_WEBHOOK_URL is not set")
        secret = os.environ.get("NOTIFICATIONS_WEBHOOK_SECRET", "")
        if not secret:
            # A URL without a secret is a mistake, not a choice: n8n would
            # refuse the request anyway.
            raise RuntimeError("NOTIFICATIONS_WEBHOOK_URL is set but NOTIFICATIONS_WEBHOOK_SECRET is not")
        return cls(base_url=base_url.rstrip("/"), secret=secret)

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path}"


def create_http_client(*, timeout: float = 30) -> httpx.Client:
    # Connection failures are retried here; any other error fails the run,
    # and Airflow retries the task.
    return httpx.Client(transport=httpx.HTTPTransport(retries=2), timeout=timeout)


class WebhookError(Exception):
    """n8n did not accept the request."""


def post(client: httpx.Client, settings: WebhookSettings, path: str, payload: dict) -> None:
    url = settings.url(path)
    response = client.post(url, json=payload, headers={SECRET_HEADER: settings.secret})
    if response.is_error:
        # n8n says in the body why it refused a payload; without it the task
        # log would only show the status code.
        raise WebhookError(f"{response.status_code} from {url}: {response.text[:500]}")
