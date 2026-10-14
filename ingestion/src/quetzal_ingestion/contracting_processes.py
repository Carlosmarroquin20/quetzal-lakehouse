"""Land Guatecompras contracting processes in the bronze layer.

One month of tender publication is the unit of work: it is one file at the
source and one partition in bronze, stored as the original zip and as a
Parquet file with one row per contracting process. Running the job again for
a month replaces both objects, so re-runs never duplicate data.

The source rewrites its files as processes move forward, including those of
past months. The checksum it publishes for each file is kept with the Parquet
object, and a month whose checksum has not changed is not downloaded again.
"""

import argparse
import hashlib
import io
import logging
from datetime import UTC, datetime
from typing import BinaryIO

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from quetzal_ingestion import guatecompras, runtime
from quetzal_ingestion.guatecompras import GuatecomprasError, Month
from quetzal_ingestion.storage import (
    StorageSettings,
    create_s3_client,
    object_metadata,
)

DATASET = "guatecompras/contracting_processes"
CHECKSUM_METADATA = "source-json-sha256"
BATCH_SIZE = 1000

# The record is stored as the JSON text the source wrote: bronze does not
# interpret it. Flattening it into tables is the job of the silver layer.
PARQUET_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("record", pa.string()),
        ("_source_file", pa.string()),
        ("_ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

log = logging.getLogger("contracting_processes")


def raw_key(month: Month) -> str:
    return (
        f"{DATASET}/raw/year={month.year}/month={month.month:02d}"
        f"/{month}_Guatecompras_json.zip"
    )


def parquet_key(month: Month) -> str:
    return (
        f"{DATASET}/parquet/year={month.year}/month={month.month:02d}"
        "/contracting_processes.parquet"
    )


class HashingReader:
    """Byte stream that computes the SHA-256 of everything read through it."""

    def __init__(self, stream: BinaryIO):
        self._stream = stream
        self._hash = hashlib.sha256()

    def read(self, size: int) -> bytes:
        chunk = self._stream.read(size)
        self._hash.update(chunk)
        return chunk

    def hexdigest(self) -> str:
        # Whatever follows the last record still belongs to the document.
        while self.read(1 << 20):
            pass
        return self._hash.hexdigest()


def stored_checksum(s3, bucket: str, month: Month) -> str | None:
    """Return the source checksum of the month already in bronze, if any."""
    metadata = object_metadata(s3, bucket, parquet_key(month))
    return None if metadata is None else metadata.get(CHECKSUM_METADATA)


def to_parquet(
    archive: bytes, month: Month, *, source_file: str, ingested_at: datetime
) -> tuple[bytes, int, str]:
    """Turn a monthly zip into Parquet.

    Return the Parquet bytes, the number of records and the SHA-256 of the
    JSON document, all obtained in a single pass over it.
    """
    buffer = io.BytesIO()
    count = 0
    with (
        guatecompras.open_json(archive) as document,
        pq.ParquetWriter(buffer, PARQUET_SCHEMA, compression="zstd") as writer,
    ):
        reader = HashingReader(document)
        batch: list[dict] = []

        def flush() -> None:
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=PARQUET_SCHEMA))
                batch.clear()

        for record, text in guatecompras.iter_records(reader):
            segment = (record.get("compiledRelease") or {}).get(
                "dataSegmentation"
            ) or {}
            if segment.get("id", str(month)) != str(month):
                raise GuatecomprasError(
                    f"file for {month} holds a record of {segment['id']}: {record.get('ocid')}"
                )
            batch.append(
                {
                    "ocid": record.get("ocid"),
                    "record": text,
                    "_source_file": source_file,
                    "_ingested_at": ingested_at,
                }
            )
            count += 1
            if len(batch) == BATCH_SIZE:
                flush()
        flush()
        checksum = reader.hexdigest()
    return buffer.getvalue(), count, checksum


def ingest_month(
    month: Month,
    *,
    http: httpx.Client,
    s3,
    bucket: str,
    ingested_at: datetime,
    force: bool = False,
) -> int | None:
    """Fetch one month and replace its partition.

    Return the number of records stored, or None when the month was skipped
    because the source has not changed it.
    """
    published = guatecompras.fetch_checksum(month, http)
    stored = stored_checksum(s3, bucket, month)
    if stored == published and not force:
        return None

    archive = guatecompras.fetch_month(month, http)
    parquet, count, checksum = to_parquet(
        archive, month, source_file=raw_key(month), ingested_at=ingested_at
    )

    # Nothing is written until the download has been checked.
    if checksum != published:
        raise GuatecomprasError(
            f"checksum of {month} is {checksum}, the service publishes {published}"
        )
    if count == 0:
        if stored is None:
            # A month that has just started may have no processes yet.
            return 0
        # An outage that serves an empty file would otherwise wipe a
        # partition that already holds data.
        raise GuatecomprasError(f"no records returned for {month}")

    # Both objects have fixed keys, so writing them again overwrites in place.
    # The Parquet file goes last and carries the checksum: if the run dies
    # between the two writes, the month does not look up to date and the next
    # run loads it again.
    s3.put_object(
        Bucket=bucket, Key=raw_key(month), Body=archive, ContentType="application/zip"
    )
    s3.put_object(
        Bucket=bucket,
        Key=parquet_key(month),
        Body=parquet,
        ContentType="application/vnd.apache.parquet",
        Metadata={CHECKSUM_METADATA: published},
    )
    return count


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    today = runtime.today_in_guatemala()
    this_month = Month(today.year, today.month)
    parser = argparse.ArgumentParser(
        prog="contracting-processes",
        description="Land Guatecompras contracting processes in the bronze layer.",
    )
    parser.add_argument(
        "--from-month",
        type=Month.parse,
        default=this_month,
        help="first month to load, as YYYY-MM (default: current month)",
    )
    parser.add_argument(
        "--to-month",
        type=Month.parse,
        default=this_month,
        help="last month to load, as YYYY-MM (default: current month)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="load a month again even if the source has not changed it",
    )
    args = parser.parse_args(argv)
    if not guatecompras.FIRST_MONTH <= args.from_month <= args.to_month <= this_month:
        parser.error(
            f"months must satisfy {guatecompras.FIRST_MONTH} <= from-month"
            f" <= to-month <= {this_month}"
        )
    return args


def main(argv: list[str] | None = None) -> None:
    runtime.configure_logging()
    args = parse_args(argv)
    settings = StorageSettings.from_env()
    s3 = create_s3_client(settings)
    ingested_at = datetime.now(UTC)

    with runtime.create_http_client() as http:
        for month in guatecompras.months_between(args.from_month, args.to_month):
            count = ingest_month(
                month,
                http=http,
                s3=s3,
                bucket=settings.bronze_bucket,
                ingested_at=ingested_at,
                force=args.force,
            )
            if count is None:
                log.info("month=%s unchanged at the source, skipped", month)
            elif count == 0:
                log.info("month=%s has no records yet, nothing stored", month)
            else:
                log.info(
                    "month=%s records=%s -> s3://%s/%s",
                    month,
                    count,
                    settings.bronze_bucket,
                    parquet_key(month),
                )


if __name__ == "__main__":
    main()
