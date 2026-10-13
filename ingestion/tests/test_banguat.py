from pathlib import Path

import httpx
import pytest

from quetzal_ingestion import banguat

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_rates_returns_one_record_per_day():
    rows = banguat.parse_rates(read_fixture("tipo_cambio_rango.xml"))

    assert len(rows) == 5
    assert rows[0] == {
        "moneda": "2",
        "fecha": "01/10/2026",
        "venta": "7.64028",
        "compra": "7.64028",
    }
    assert rows[-1]["fecha"] == "05/10/2026"


def test_parse_rates_keeps_values_as_source_text():
    rows = banguat.parse_rates(read_fixture("tipo_cambio_rango.xml"))

    assert all(isinstance(value, str) for row in rows for value in row.values())


def test_parse_rates_accepts_a_response_without_records():
    assert banguat.parse_rates(read_fixture("tipo_cambio_rango_empty.xml")) == []


def test_parse_rates_rejects_a_truncated_response():
    xml = read_fixture("tipo_cambio_rango.xml").replace(
        b"<TotalItems>5</TotalItems>", b"<TotalItems>6</TotalItems>"
    )

    with pytest.raises(
        banguat.BanguatError, match="declares '6' records but contains 5"
    ):
        banguat.parse_rates(xml)


def test_parse_rates_rejects_a_response_that_is_not_xml():
    with pytest.raises(banguat.BanguatError, match="not well-formed"):
        banguat.parse_rates(b"<html><body>Service unavailable")


def test_parse_rates_rejects_xml_without_a_result():
    with pytest.raises(banguat.BanguatError, match="no TipoCambioRangoResult"):
        banguat.parse_rates(b"<other>response</other>")


def test_fetch_year_requests_the_whole_calendar_year():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["action"] = request.headers["SOAPAction"]
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, content=b"<raw/>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = banguat.fetch_year(2025, client)

    assert raw == b"<raw/>"
    assert seen["url"] == banguat.SERVICE_URL
    assert seen["action"] == '"http://www.banguat.gob.gt/variables/ws/TipoCambioRango"'
    assert "<fechainit>01/01/2025</fechainit>" in seen["body"]
    assert "<fechafin>31/12/2025</fechafin>" in seen["body"]


def test_fetch_year_fails_on_a_soap_fault():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"<soap:Fault/>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with client, pytest.raises(httpx.HTTPStatusError):
        banguat.fetch_year(2025, client)
