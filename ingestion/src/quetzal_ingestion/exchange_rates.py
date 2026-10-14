"""Land Banco de Guatemala exchange rates in the bronze layer.

One calendar year is the unit of work: it is fetched with a single request and
stored under a single partition, as the exact response and as a Parquet copy.
Running the job again for a year replaces both objects, so re-runs never
duplicate data.
"""

import argparse
import io
import logging
from datetime import UTC, datetime

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from quetzal_ingestion import banguat, runtime
from quetzal_ingestion.storage import StorageSettings, create_s3_client

DATASET = "banguat/exchange_rates"

# Every source field is stored as text: bronze does not interpret values.
PARQUET_SCHEMA = pa.schema(
    [(field, pa.string()) for field in banguat.FIELDS]
    + [
        ("_source_file", pa.string()),
        ("_ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

log = logging.getLogger("exchange_rates")


def raw_key(year: int) -> str:
    return f"{DATASET}/raw/year={year}/response.xml"


def parquet_key(year: int) -> str:
    return f"{DATASET}/parquet/year={year}/exchange_rates.parquet"


def to_parquet(rows: list[dict], *, source_file: str, ingested_at: datetime) -> bytes:
    """Serialize the records, adding where and when they were obtained."""
    records = [
        {**row, "_source_file": source_file, "_ingested_at": ingested_at}
        for row in rows
    ]
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(records, schema=PARQUET_SCHEMA), buffer)
    return buffer.getvalue()


def check_rows(rows: list[dict], year: int) -> None:
    """Refuse responses that must not replace what is already stored."""
    if not rows:
        # An outage that answers with an empty result would otherwise wipe a
        # partition that already holds data.
        raise banguat.BanguatError(f"no records returned for {year}")
    strays = [
        row["fecha"] for row in rows if not str(row["fecha"]).endswith(f"/{year}")
    ]
    if strays:
        raise banguat.BanguatError(f"records outside {year}: {strays[:3]}")


def ingest_year(
    year: int, *, http: httpx.Client, s3, bucket: str, ingested_at: datetime
) -> int:
    """Fetch one year and replace its partition. Return the number of records."""
    raw = banguat.fetch_year(year, http)
    rows = banguat.parse_rates(raw)
    check_rows(rows, year)

    # Both objects have fixed keys, so writing them again overwrites in place.
    # The raw response goes first: the Parquet file names it as its source.
    s3.put_object(Bucket=bucket, Key=raw_key(year), Body=raw, ContentType="text/xml")
    s3.put_object(
        Bucket=bucket,
        Key=parquet_key(year),
        Body=to_parquet(rows, source_file=raw_key(year), ingested_at=ingested_at),
        ContentType="application/vnd.apache.parquet",
    )
    return len(rows)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    this_year = runtime.today_in_guatemala().year
    parser = argparse.ArgumentParser(
        prog="exchange-rates",
        description="Land Banco de Guatemala exchange rates in the bronze layer.",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=this_year,
        help="first year to load (default: current year)",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=this_year,
        help="last year to load (default: current year)",
    )
    args = parser.parse_args(argv)
    if not banguat.FIRST_YEAR <= args.from_year <= args.to_year <= this_year:
        parser.error(
            f"years must satisfy {banguat.FIRST_YEAR} <= from-year <= to-year <= {this_year}"
        )
    return args


def main(argv: list[str] | None = None) -> None:
    runtime.configure_logging()
    args = parse_args(argv)
    settings = StorageSettings.from_env()
    s3 = create_s3_client(settings)
    ingested_at = datetime.now(UTC)

    with runtime.create_http_client() as http:
        for year in range(args.from_year, args.to_year + 1):
            count = ingest_year(
                year,
                http=http,
                s3=s3,
                bucket=settings.bronze_bucket,
                ingested_at=ingested_at,
            )
            log.info(
                "year=%s records=%s -> s3://%s/%s",
                year,
                count,
                settings.bronze_bucket,
                parquet_key(year),
            )


if __name__ == "__main__":
    main()
