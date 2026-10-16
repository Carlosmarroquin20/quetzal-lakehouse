"""Report a failed task to n8n, which sends the alert.

Airflow calls report_failure when a task has failed for good, after its
retries. It runs inside the Airflow worker rather than in one of the
project's images, so it uses only the standard library, and it can be tested
without installing Airflow.
"""

import json
import logging
import os
import urllib.request
from datetime import UTC, datetime

# Has to match the header n8n's webhooks check, as the digest job does.
SECRET_HEADER = "X-Webhook-Secret"
FAILURE_PATH = "pipeline-failure"
KIND = "pipeline_failure"
# Raised whenever a field is removed or changes meaning, so the receiving
# workflow can refuse a payload it was not written for.
SCHEMA_VERSION = 1
# Enough to tell one failure from another in a chat message; the full error
# stays in the task log.
ERROR_LENGTH = 500

log = logging.getLogger(__name__)


def failure_payload(context: dict, failed_at: datetime) -> dict:
    ti = context["ti"]
    exception = context.get("exception")
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "dag_id": ti.dag_id,
        "task_id": ti.task_id,
        "run_id": ti.run_id,
        "try_number": ti.try_number,
        "failed_at": failed_at.isoformat(),
        "error": f"{type(exception).__name__}: {exception}"[:ERROR_LENGTH] if exception else None,
    }


def post_json(url: str, payload: dict, secret: str, *, timeout: float = 10) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", SECRET_HEADER: secret},
    )
    # urlopen raises on any answer outside 2xx.
    with urllib.request.urlopen(request, timeout=timeout):
        pass


def report_failure(context: dict) -> None:
    """The on_failure_callback of every task."""
    base_url = os.environ.get("NOTIFICATIONS_WEBHOOK_URL", "")
    if not base_url:
        return
    secret = os.environ.get("NOTIFICATIONS_WEBHOOK_SECRET", "")
    if not secret:
        log.warning("NOTIFICATIONS_WEBHOOK_SECRET is not set; the failure was not reported")
        return
    url = f"{base_url.rstrip('/')}/{FAILURE_PATH}"
    try:
        post_json(url, failure_payload(context, datetime.now(UTC)), secret)
    except OSError as error:
        # The task has already failed and Airflow shows it; an alert that
        # cannot be sent must not add a second error on top of it.
        log.warning("could not report the failure to %s: %s", url, error)
