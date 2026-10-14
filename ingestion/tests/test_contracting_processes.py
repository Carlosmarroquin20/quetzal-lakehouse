import io
from datetime import UTC, datetime

import httpx
import ocds_samples
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError

from quetzal_ingestion import contracting_processes
from quetzal_ingestion.guatecompras import GuatecomprasError, Month

MONTH = Month(2026, 9)
INGESTED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
RAW = ("bronze", contracting_processes.raw_key(MONTH))
PARQUET = ("bronze", contracting_processes.parquet_key(MONTH))


class FakeS3:
    """Stands in for the S3 client: a put replaces whatever the key held."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict] = {}

    def put_object(self, *, Bucket, Key, Body, Metadata=None, **_):
        self.objects[(Bucket, Key)] = Body
        self.metadata[(Bucket, Key)] = Metadata or {}

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"Metadata": self.metadata[(Bucket, Key)]}


class Source:
    """Stands in for Guatecompras, counting how often the file is downloaded."""

    def __init__(self, document: bytes, published: str | None = None):
        self.archive = ocds_samples.archive(document)
        self.published = published or ocds_samples.checksum(document)
        self.downloads = 0

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/file/sha/2026/9":
                return httpx.Response(200, text=self.published)
            assert request.url.path == "/file/json/2026/9"
            self.downloads += 1
            return httpx.Response(200, content=self.archive)

        return httpx.Client(transport=httpx.MockTransport(handler))


def ingest(s3: FakeS3, source: Source, **options) -> int | None:
    with source.client() as http:
        return contracting_processes.ingest_month(
            MONTH, http=http, s3=s3, bucket="bronze", ingested_at=INGESTED_AT, **options
        )


def three_records() -> bytes:
    return ocds_samples.package([ocds_samples.record(n) for n in (1, 2, 3)])


def stored_table(s3: FakeS3):
    return pq.read_table(io.BytesIO(s3.objects[PARQUET]))


def test_keys_are_partitioned_by_year_and_month():
    assert RAW[1] == (
        "guatecompras/contracting_processes/raw/year=2026/month=09/2026-09_Guatecompras_json.zip"
    )
    assert PARQUET[1] == (
        "guatecompras/contracting_processes/parquet/year=2026/month=09/contracting_processes.parquet"
    )


def test_ingest_month_stores_the_original_zip_and_one_row_per_record():
    s3, source = FakeS3(), Source(three_records())

    count = ingest(s3, source)

    assert count == 3
    assert s3.objects[RAW] == source.archive
    table = stored_table(s3)
    assert table.column_names == ["ocid", "record", "_source_file", "_ingested_at"]
    rows = table.to_pylist()
    assert [row["ocid"] for row in rows] == [
        "ocds-xqjsxa-1",
        "ocds-xqjsxa-2",
        "ocds-xqjsxa-3",
    ]
    assert rows[0]["record"].encode("utf-8") in three_records()
    assert rows[0]["_source_file"] == RAW[1]
    assert rows[0]["_ingested_at"] == INGESTED_AT


def test_a_month_the_source_has_not_changed_is_not_downloaded_again():
    s3, source = FakeS3(), Source(three_records())

    ingest(s3, source)
    second = ingest(s3, source)

    assert second is None
    assert source.downloads == 1


def test_a_month_the_source_has_changed_replaces_the_stored_one():
    s3 = FakeS3()
    ingest(s3, Source(three_records()))
    changed = Source(
        ocds_samples.package([ocds_samples.record(n) for n in (1, 2, 3, 4)])
    )

    count = ingest(s3, changed)

    assert count == 4
    assert set(s3.objects) == {RAW, PARQUET}
    assert stored_table(s3).num_rows == 4


def test_force_loads_an_unchanged_month_again():
    s3, source = FakeS3(), Source(three_records())

    ingest(s3, source)
    count = ingest(s3, source, force=True)

    assert count == 3
    assert source.downloads == 2
    assert stored_table(s3).num_rows == 3


def test_a_download_that_does_not_match_the_published_checksum_is_rejected():
    s3 = FakeS3()

    with pytest.raises(GuatecomprasError, match="checksum of 2026-09"):
        ingest(s3, Source(three_records(), published="0" * 64))

    assert s3.objects == {}


def test_a_file_holding_records_of_another_month_is_rejected():
    s3 = FakeS3()
    document = ocds_samples.package(
        [ocds_samples.record(1), ocds_samples.record(2, month="2026-08")]
    )

    with pytest.raises(GuatecomprasError, match="holds a record of 2026-08"):
        ingest(s3, Source(document))

    assert s3.objects == {}


def test_an_empty_file_does_not_replace_stored_data():
    s3 = FakeS3()
    ingest(s3, Source(three_records()))
    stored = dict(s3.objects)

    with pytest.raises(GuatecomprasError, match="no records returned for 2026-09"):
        ingest(s3, Source(ocds_samples.package([])))

    assert s3.objects == stored


def test_an_empty_file_for_a_month_never_loaded_stores_nothing():
    s3 = FakeS3()

    count = ingest(s3, Source(ocds_samples.package([])))

    assert count == 0
    assert s3.objects == {}


def test_month_range_must_be_within_what_the_service_offers(capsys):
    with pytest.raises(SystemExit):
        contracting_processes.parse_args(["--from-month", "2019-12"])
    with pytest.raises(SystemExit):
        contracting_processes.parse_args(
            ["--from-month", "2026-02", "--to-month", "2026-01"]
        )
    assert "months must satisfy 2020-01 <= from-month" in capsys.readouterr().err
