"""Daily dumps of the DuckLake catalogs, kept for a fixed number of days.

The catalogs record which Parquet files make up each version of each table
of silver and gold. Without them the files are still in the buckets, but
nothing says which belong to which table, and the way back is a rebuild from
bronze. This job dumps each prod catalog with pg_dump to the backups bucket,
then deletes the dumps older than BACKUP_KEEP_DAYS.

That number must stay below the days of versions the catalogs keep
(maintain_lake, 30): a dump points at files, and maintain_lake deletes the
files of versions older than that, so an older dump would point at nothing.
"""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config

log = logging.getLogger("catalog_backup")


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    region: str
    bucket: str
    catalog_host: str
    catalog_user: str
    catalog_password: str
    catalogs: tuple[str, ...]
    keep_days: int
    catalog_port: int = 5432
    # As in the other jobs: an endpoint for an S3-compatible store, and a key
    # pair given as a pair or not at all (then the standard AWS chain).
    endpoint_url: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        key_id = os.environ.get("S3_ACCESS_KEY_ID") or None
        secret = os.environ.get("S3_SECRET_ACCESS_KEY") or None
        if (key_id is None) != (secret is None):
            raise RuntimeError(
                "set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither"
            )
        catalogs = tuple(
            name.strip() for name in _required("BACKUP_CATALOGS").split(",") if name.strip()
        )
        keep_days = int(os.environ.get("BACKUP_KEEP_DAYS", "14"))
        if keep_days < 1:
            raise RuntimeError("BACKUP_KEEP_DAYS must be at least 1")
        return cls(
            region=_required("S3_REGION"),
            bucket=_required("S3_BUCKET_BACKUPS"),
            catalog_host=_required("LAKE_CATALOG_HOST"),
            catalog_port=int(os.environ.get("LAKE_CATALOG_PORT", "5432")),
            catalog_user=_required("LAKE_CATALOG_USER"),
            catalog_password=_required("LAKE_CATALOG_PASSWORD"),
            catalogs=catalogs,
            keep_days=keep_days,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            access_key_id=key_id,
            secret_access_key=secret,
        )


def today_in_guatemala() -> date:
    return datetime.now(ZoneInfo("America/Guatemala")).date()


def dump_key(catalog: str, day: date) -> str:
    """One dump per catalog and day; a second run the same day replaces it."""
    return f"catalog/{catalog}/{day.isoformat()}.dump"


def expired_keys(keys: list[str], catalog: str, today: date, keep_days: int) -> list[str]:
    """The dumps of a catalog older than keep_days, today counting as one."""
    oldest_kept = today - timedelta(days=keep_days - 1)
    prefix = f"catalog/{catalog}/"
    expired = []
    for key in keys:
        name = key.removeprefix(prefix)
        if not key.startswith(prefix) or not name.endswith(".dump"):
            continue
        try:
            day = date.fromisoformat(name.removesuffix(".dump"))
        except ValueError:
            continue
        if day < oldest_kept:
            expired.append(key)
    return sorted(expired)


def pg_dump_command(settings: Settings, catalog: str, path: Path) -> list[str]:
    # The password goes through the environment (PGPASSWORD), never the
    # command line, which other processes on the machine can read.
    return [
        "pg_dump",
        "--host", settings.catalog_host,
        "--port", str(settings.catalog_port),
        "--username", settings.catalog_user,
        "--format", "custom",
        "--file", str(path),
        catalog,
    ]


def create_s3_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        config=Config(
            s3={"addressing_style": "path" if settings.endpoint_url else "auto"}
        ),
    )


def back_up(settings: Settings, s3, today: date, run=subprocess.run) -> list[str]:
    """Dump and upload every catalog, then delete the expired dumps.

    Return the keys written. Dumps are deleted only after every catalog was
    dumped, so a failing run never leaves fewer backups than it found.
    """
    written = []
    env = {**os.environ, "PGPASSWORD": settings.catalog_password}
    with tempfile.TemporaryDirectory() as directory:
        for catalog in settings.catalogs:
            path = Path(directory) / f"{catalog}.dump"
            run(pg_dump_command(settings, catalog, path), env=env, check=True)
            key = dump_key(catalog, today)
            s3.upload_file(str(path), settings.bucket, key)
            log.info("catalog=%s bytes=%s -> s3://%s/%s", catalog, path.stat().st_size, settings.bucket, key)
            written.append(key)

    for catalog in settings.catalogs:
        listing = s3.list_objects_v2(Bucket=settings.bucket, Prefix=f"catalog/{catalog}/")
        keys = [item["Key"] for item in listing.get("Contents", [])]
        for key in expired_keys(keys, catalog, today, settings.keep_days):
            s3.delete_object(Bucket=settings.bucket, Key=key)
            log.info("catalog=%s expired dump deleted: %s", catalog, key)
    return written
