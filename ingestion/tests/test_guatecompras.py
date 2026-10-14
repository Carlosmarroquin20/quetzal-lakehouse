import io
import json

import httpx
import ocds_samples
import pytest

from quetzal_ingestion import guatecompras
from quetzal_ingestion.guatecompras import GuatecomprasError, Month


def client_answering(routes: dict[str, httpx.Response]) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: routes[request.url.path])
    )


def test_month_is_read_from_and_written_as_year_dash_month():
    assert Month.parse("2026-09") == Month(2026, 9)
    assert str(Month(2026, 9)) == "2026-09"


@pytest.mark.parametrize("text", ["2026-9", "2026-13", "2026/09", "september"])
def test_month_rejects_other_forms(text):
    with pytest.raises(ValueError):
        Month.parse(text)


def test_months_between_crosses_the_year_boundary():
    months = guatecompras.months_between(Month(2025, 11), Month(2026, 2))

    assert [str(month) for month in months] == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_fetch_month_asks_for_the_month_without_a_leading_zero():
    with client_answering(
        {"/file/json/2026/9": httpx.Response(200, content=b"zip")}
    ) as client:
        assert guatecompras.fetch_month(Month(2026, 9), client) == b"zip"


def test_fetch_checksum_returns_the_published_hash():
    published = "A" * 64
    with client_answering(
        {"/file/sha/2026/9": httpx.Response(200, text=published + "\n")}
    ) as client:
        assert guatecompras.fetch_checksum(Month(2026, 9), client) == "a" * 64


def test_fetch_checksum_rejects_anything_that_is_not_a_hash():
    client = client_answering(
        {"/file/sha/2026/9": httpx.Response(200, text="<html>error</html>")}
    )
    with client, pytest.raises(GuatecomprasError, match="not a SHA-256"):
        guatecompras.fetch_checksum(Month(2026, 9), client)


def test_open_json_rejects_a_file_that_is_not_a_zip():
    with pytest.raises(GuatecomprasError, match="not a zip"):
        guatecompras.open_json(b"<html>Service unavailable</html>")


def test_open_json_rejects_a_zip_with_unexpected_content():
    with pytest.raises(GuatecomprasError, match="expected one JSON file"):
        guatecompras.open_json(ocds_samples.archive(b"{}", name="readme.txt"))


@pytest.mark.parametrize("chunk_size", [1, 7, 64, 1 << 20])
def test_iter_records_yields_each_record_with_its_exact_text(chunk_size):
    records = [ocds_samples.record(1), ocds_samples.record(2), ocds_samples.record(3)]
    document = ocds_samples.package(records)

    found = list(guatecompras.iter_records(io.BytesIO(document), chunk_size=chunk_size))

    assert [parsed for parsed, _ in found] == records
    for _, text in found:
        # The text is a slice of the document, not a re-encoding of it.
        assert text.encode("utf-8") in document
        assert (
            json.loads(text)["compiledRelease"]["tender"]["title"]
            == "Señal y conversión"
        )


def test_iter_records_handles_a_package_without_records():
    assert list(guatecompras.iter_records(io.BytesIO(ocds_samples.package([])))) == []


def test_iter_records_rejects_a_document_cut_off_mid_record():
    document = ocds_samples.package([ocds_samples.record(1), ocds_samples.record(2)])

    with pytest.raises(GuatecomprasError, match="cut off"):
        list(guatecompras.iter_records(io.BytesIO(document[:-40])))


def test_iter_records_rejects_a_document_without_a_records_array():
    with pytest.raises(GuatecomprasError, match="no records array"):
        list(guatecompras.iter_records(io.BytesIO(b'{"releases": []}')))
