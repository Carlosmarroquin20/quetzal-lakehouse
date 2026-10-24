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


class Months:
    """Stands in for Guatecompras serving several months, some of them broken."""

    def __init__(self, broken_checksum=(), unavailable=()):
        self.documents = {
            month: ocds_samples.package(
                [ocds_samples.record(n, month=str(month)) for n in (1, 2)]
            )
            for month in (Month(2026, 7), Month(2026, 8), Month(2026, 9))
        }
        self.broken_checksum = set(broken_checksum)
        self.unavailable = set(unavailable)

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            kind, year, number = request.url.path.split("/")[2:]
            month = Month(int(year), int(number))
            if month in self.unavailable:
                return httpx.Response(503)
            document = self.documents[month]
            if kind == "sha":
                published = ocds_samples.checksum(document)
                return httpx.Response(
                    200, text="0" * 64 if month in self.broken_checksum else published
                )
            return httpx.Response(
                200, content=ocds_samples.archive(document, name=f"{month}_Guatecompras.json")
            )

        return httpx.Client(transport=httpx.MockTransport(handler))


def ingest_three_months(s3, source: Months) -> list[str]:
    with source.client() as http:
        return contracting_processes.ingest_months(
            [Month(2026, 7), Month(2026, 8), Month(2026, 9)],
            http=http, s3=s3, bucket="bronze", ingested_at=INGESTED_AT,
        )


def stored_months(s3: FakeS3) -> set[str]:
    return {
        str(month)
        for month in (Month(2026, 7), Month(2026, 8), Month(2026, 9))
        if ("bronze", contracting_processes.parquet_key(month)) in s3.objects
    }


def test_a_broken_month_does_not_hold_back_the_months_after_it():
    s3 = FakeS3()

    failures = ingest_three_months(s3, Months(broken_checksum={Month(2026, 7)}))

    assert stored_months(s3) == {"2026-08", "2026-09"}
    assert len(failures) == 1
    assert failures[0].startswith("2026-07: checksum of 2026-07")


def test_a_broken_month_keeps_the_version_bronze_holds():
    s3 = FakeS3()
    ingest_three_months(s3, Months())
    before = s3.objects[("bronze", contracting_processes.parquet_key(Month(2026, 8)))]

    source = Months(broken_checksum={Month(2026, 8)})
    source.documents[Month(2026, 8)] = ocds_samples.package(
        [ocds_samples.record(n, month="2026-08") for n in (1, 2, 3)]
    )
    failures = ingest_three_months(s3, source)

    assert [f[:7] for f in failures] == ["2026-08"]
    assert s3.objects[("bronze", contracting_processes.parquet_key(Month(2026, 8)))] == before


def test_a_month_the_service_cannot_serve_is_a_failure_of_that_month_only():
    s3 = FakeS3()

    failures = ingest_three_months(s3, Months(unavailable={Month(2026, 8)}))

    assert stored_months(s3) == {"2026-07", "2026-09"}
    assert [f[:7] for f in failures] == ["2026-08"]


def test_an_unreachable_store_still_stops_the_run():
    class BrokenS3(FakeS3):
        def put_object(self, **_):
            raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")

    with pytest.raises(ClientError):
        ingest_three_months(BrokenS3(), Months())


def test_the_run_fails_naming_the_months_it_could_not_load(monkeypatch):
    monkeypatch.setattr(contracting_processes, "StorageSettings", type(
        "Settings", (), {"from_env": staticmethod(lambda: type("S", (), {"bronze_bucket": "bronze"})())}
    ))
    monkeypatch.setattr(contracting_processes, "create_s3_client", lambda settings: FakeS3())
    source = Months(broken_checksum={Month(2026, 8)})
    monkeypatch.setattr(contracting_processes.runtime, "create_http_client", source.client)
    monkeypatch.setattr(contracting_processes.runtime, "today_in_guatemala",
                        lambda: datetime(2026, 9, 30).date())

    with pytest.raises(SystemExit) as stopped:
        contracting_processes.main(["--from-month", "2026-07", "--to-month", "2026-09"])

    assert "1 month(s) not loaded: 2026-08: checksum of 2026-08" in str(stopped.value)
