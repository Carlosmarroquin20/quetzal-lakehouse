"""Print or post the daily digest: ``python -m quetzal_notifications digest [options]``."""

import argparse
import json
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from quetzal_notifications import digest, gold, webhook

# Exit code when posting is asked for but no webhook is configured. Airflow
# marks the task as skipped on it, so the pipeline still runs without n8n.
NOT_CONFIGURED = 3


def today_in_guatemala() -> date:
    # The job may run on a machine set to UTC, where the date changes six
    # hours before it does in Guatemala.
    return datetime.now(ZoneInfo("America/Guatemala")).date()


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "digest":
        sys.exit("usage: python -m quetzal_notifications digest [options]")

    parser = argparse.ArgumentParser(prog="python -m quetzal_notifications digest")
    parser.add_argument(
        "--run-date",
        type=date.fromisoformat,
        default=None,
        help="Day of the run, as YYYY-MM-DD (default: today in Guatemala).",
    )
    parser.add_argument("--run-id", default=None, help="Identifier of the run, such as Airflow's.")
    parser.add_argument(
        "--post",
        action="store_true",
        help="Also post the digest to n8n, at NOTIFICATIONS_WEBHOOK_URL.",
    )
    args = parser.parse_args(argv[1:])

    # Checked before reading gold, so a run without n8n ends at once.
    settings = None
    if args.post:
        try:
            settings = webhook.WebhookSettings.from_env()
        except webhook.NotConfigured as error:
            print(f"{error}; nothing posted", file=sys.stderr)
            sys.exit(NOT_CONFIGURED)

    payload = digest.build(
        gold.connect(),
        run_date=args.run_date or today_in_guatemala(),
        generated_at=datetime.now(UTC),
        run_id=args.run_id,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    if settings:
        with webhook.create_http_client() as client:
            webhook.post(client, settings, webhook.DIGEST_PATH, payload)
        print(f"posted to {settings.url(webhook.DIGEST_PATH)}", file=sys.stderr)


if __name__ == "__main__":
    main()
