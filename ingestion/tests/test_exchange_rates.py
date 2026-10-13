import io
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from quetzal_ingestion import banguat, exchange_rates

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSE = (FIXTURES / "tipo_cambio_rango.xml").read_bytes()
EMPTY_RESPONSE = (FIXTURES / "tipo_cambio_rango_empty.xml").read_bytes()
INGESTED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class FakeS3:
    """Stands in for the S3 client: a put replaces whatever the key held."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, **_):
        self.objects[(Bucket, Key)] = Body


def http_returning(content: bytes) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content))
    )


def ingest(s3: FakeS3, content: bytes, year: int = 2026) -> int:
    with http_returning(content) as http:
        return exchange_rates.ingest_year(
            year, http=http, s3=s3, bucket="bronze", ingested_at=INGESTED_AT
        )


def test_keys_are_partitioned_by_year():
    assert (
        exchange_rates.raw_key(2026)
        == "banguat/exchange_rates/raw/year=2026/response.xml"
    )
    assert (
        exchange_rates.parquet_key(2026)
        == "banguat/exchange_rates/parquet/year=2026/exchange_rates.parquet"
    )


def test_ingest_year_stores_the_exact_response_and_a_parquet_copy():
    s3 = FakeS3()

    count = ingest(s3, RESPONSE)

    assert count == 5
    assert s3.objects[("bronze", exchange_rates.raw_key(2026))] == RESPONSE
    table = pq.read_table(
        io.BytesIO(s3.objects[("bronze", exchange_rates.parquet_key(2026))])
    )
    assert table.num_rows == 5
    assert table.column_names == [
        "moneda",
        "fecha",
        "venta",
        "compra",
        "_source_file",
        "_ingested_at",
    ]
    first = table.slice(0, 1).to_pylist()[0]
    assert first["fecha"] == "01/10/2026"
    assert first["venta"] == "7.64028"
    assert first["_source_file"] == exchange_rates.raw_key(2026)
    assert first["_ingested_at"] == INGESTED_AT


def test_running_twice_does_not_duplicate_anything():
    s3 = FakeS3()

    ingest(s3, RESPONSE)
    keys_after_first_run = set(s3.objects)
    ingest(s3, RESPONSE)

    assert set(s3.objects) == keys_after_first_run
    table = pq.read_table(
        io.BytesIO(s3.objects[("bronze", exchange_rates.parquet_key(2026))])
    )
    assert table.num_rows == 5


def test_an_empty_response_does_not_replace_stored_data():
    s3 = FakeS3()
    ingest(s3, RESPONSE)
    stored = dict(s3.objects)

    with pytest.raises(banguat.BanguatError, match="no records returned for 2026"):
        ingest(s3, EMPTY_RESPONSE)

    assert s3.objects == stored


def test_records_from_another_year_are_rejected():
    s3 = FakeS3()

    with pytest.raises(banguat.BanguatError, match="records outside 2025"):
        ingest(s3, RESPONSE, year=2025)

    assert s3.objects == {}


def test_year_range_must_be_within_what_the_service_offers(capsys):
    with pytest.raises(SystemExit):
        exchange_rates.parse_args(["--from-year", "1980"])
    with pytest.raises(SystemExit):
        exchange_rates.parse_args(["--from-year", "2026", "--to-year", "2025"])
    assert "years must satisfy 1989 <= from-year" in capsys.readouterr().err
