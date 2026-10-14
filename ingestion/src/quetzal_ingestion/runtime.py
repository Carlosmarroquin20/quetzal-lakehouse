"""What every ingestion job needs in order to run: a clock, an HTTP client and logging."""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

USER_AGENT = (
    "quetzal-lakehouse (+https://github.com/Carlosmarroquin20/quetzal-lakehouse)"
)


def today_in_guatemala() -> date:
    # Jobs may run on a machine set to UTC, where the date changes six hours
    # before it does in Guatemala.
    return datetime.now(ZoneInfo("America/Guatemala")).date()


def create_http_client(*, timeout: float = 30) -> httpx.Client:
    # Connection failures are retried here. Anything else stops the run: a
    # failed unit of work leaves what is stored intact and can be re-run.
    return httpx.Client(
        transport=httpx.HTTPTransport(retries=2),
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
