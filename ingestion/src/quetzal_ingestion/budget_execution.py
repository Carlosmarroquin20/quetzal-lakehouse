"""Land MINFIN budget execution workbooks in the bronze layer.

The workbooks are downloaded by hand into a landing folder. One fiscal year is
the unit of work: each workbook holds one year, read from its content rather
than from its file name, and is stored under that year's partition as the
original file and as a Parquet copy. Loading a workbook for a year replaces
what bronze held for it, so only the latest file of each year is kept.
"""

import argparse
import hashlib
import io
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from quetzal_ingestion import minfin, runtime
from quetzal_ingestion.minfin import MinfinError
from quetzal_ingestion.storage import (
    StorageSettings,
    create_s3_client,
    object_metadata,
)

DATASET = "minfin/central_government_expenditure"
CHECKSUM_METADATA = "source-sha256"
BATCH_SIZE = 10_000
YEAR_COLUMN = minfin.COLUMNS.index("ejercicio")

# Every cell is stored as text: bronze does not interpret values.
PARQUET_SCHEMA = pa.schema(
    [(column, pa.string()) for column in minfin.COLUMNS]
    + [
        ("_source_file", pa.string()),
        ("_ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)

log = logging.getLogger("budget_execution")


def raw_key(year: int) -> str:
    return f"{DATASET}/raw/year={year}/budget_execution.xlsx"


def parquet_key(year: int) -> str:
    return f"{DATASET}/parquet/year={year}/budget_execution.parquet"


@dataclass(frozen=True)
class Workbook:
    path: Path
    year: int
    rows: int
    checksum: str
    parquet: bytes


def landed_files(landing_dir: Path) -> list[Path]:
    # Excel leaves "~$name.xlsx" lock files next to a workbook it has open.
    return sorted(
        path for path in landing_dir.glob("*.xlsx") if not path.name.startswith("~$")
    )


def read_workbook(path: Path, *, ingested_at: datetime) -> Workbook:
    """Read a workbook into Parquet and find the fiscal year it holds."""
    buffer = io.BytesIO()
    year = None
    count = 0
    with pq.ParquetWriter(buffer, PARQUET_SCHEMA, compression="zstd") as writer:
        batch: list[dict] = []
        for row in minfin.read_rows(path):
            if year is None:
                year = _fiscal_year(row[YEAR_COLUMN], path)
            elif row[YEAR_COLUMN] != str(year):
                raise MinfinError(
                    f"{path.name} mixes fiscal years: {year} and {row[YEAR_COLUMN]}"
                )
            batch.append(
                {
                    **dict(zip(minfin.COLUMNS, row, strict=True)),
                    "_source_file": raw_key(year),
                    "_ingested_at": ingested_at,
                }
            )
            count += 1
            if len(batch) == BATCH_SIZE:
                writer.write_table(pa.Table.from_pylist(batch, schema=PARQUET_SCHEMA))
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=PARQUET_SCHEMA))
    if count == 0:
        # An empty workbook would otherwise replace a year that holds data.
        raise MinfinError(f"{path.name} has no budget lines")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return Workbook(path, year, count, checksum, buffer.getvalue())


def _fiscal_year(value: str | None, path: Path) -> int:
    if value is None or not value.isdigit():
        raise MinfinError(f"{path.name} has no valid fiscal year: {value!r}")
    return int(value)


def check_one_file_per_year(workbooks: list[Workbook]) -> None:
    """Refuse to guess which of two files of the same year is the right one."""
    repeated = [year for year, n in Counter(w.year for w in workbooks).items() if n > 1]
    if repeated:
        names = [w.path.name for w in workbooks if w.year in repeated]
        raise MinfinError(f"more than one file for fiscal year {repeated}: {names}")


def ingest_workbook(
    workbook: Workbook, *, s3, bucket: str, force: bool = False
) -> bool:
    """Replace the year's partition with the workbook.

    Return False, writing nothing, when bronze already holds this exact file.
    """
    stored = object_metadata(s3, bucket, parquet_key(workbook.year)) or {}
    if stored.get(CHECKSUM_METADATA) == workbook.checksum and not force:
        return False

    # Both objects have fixed keys, so loading a year again overwrites it. The
    # Parquet file goes last and carries the checksum: if the run dies between
    # the two writes, the year does not look up to date and the next run loads
    # it again.
    s3.put_object(
        Bucket=bucket,
        Key=raw_key(workbook.year),
        Body=workbook.path.read_bytes(),
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # S3 metadata only allows ASCII, so the name is percent-encoded.
        Metadata={"original-file-name": quote(workbook.path.name)},
    )
    s3.put_object(
        Bucket=bucket,
        Key=parquet_key(workbook.year),
        Body=workbook.parquet,
        ContentType="application/vnd.apache.parquet",
        Metadata={CHECKSUM_METADATA: workbook.checksum},
    )
    return True


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="budget-execution",
        description="Land MINFIN budget execution workbooks in the bronze layer.",
    )
    parser.add_argument(
        "--landing-dir",
        type=Path,
        default=Path("/landing/minfin"),
        help="folder holding the downloaded workbooks (default: /landing/minfin)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="load a workbook again even if bronze already holds the same file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    runtime.configure_logging()
    args = parse_args(argv)
    files = landed_files(args.landing_dir)
    if not files:
        log.info("no workbooks in %s, nothing to load", args.landing_dir)
        return

    settings = StorageSettings.from_env()
    s3 = create_s3_client(settings)
    ingested_at = datetime.now(UTC)

    # Every file is read and checked before anything is written.
    workbooks = [read_workbook(path, ingested_at=ingested_at) for path in files]
    check_one_file_per_year(workbooks)

    for workbook in workbooks:
        if ingest_workbook(
            workbook, s3=s3, bucket=settings.bronze_bucket, force=args.force
        ):
            log.info(
                "year=%s rows=%s from %s -> s3://%s/%s",
                workbook.year,
                workbook.rows,
                workbook.path.name,
                settings.bronze_bucket,
                parquet_key(workbook.year),
            )
        else:
            log.info(
                "year=%s already loaded from this same file, skipped", workbook.year
            )


if __name__ == "__main__":
    main()
