"""Client for the Banco de Guatemala exchange rate web service.

The service speaks SOAP over HTTP. Only the ``TipoCambioRango`` operation is
used: it returns the reference rate of the quetzal against the US dollar for
every calendar day in a date range.
"""

from xml.etree.ElementTree import ParseError

import httpx
from defusedxml import ElementTree

SERVICE_URL = "https://www.banguat.gob.gt/variables/ws/TipoCambio.asmx"
NAMESPACE = "http://www.banguat.gob.gt/variables/ws/"
OPERATION = "TipoCambioRango"

# The service returns nothing before 1989-11-06 (checked on 2026-10-13).
FIRST_YEAR = 1989

# Fields of each daily record, with the names the service uses.
FIELDS = ("moneda", "fecha", "venta", "compra")

_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <TipoCambioRango xmlns="{namespace}">
      <fechainit>01/01/{year}</fechainit>
      <fechafin>31/12/{year}</fechafin>
    </TipoCambioRango>
  </soap:Body>
</soap:Envelope>"""


class BanguatError(Exception):
    """The service answered with something that is not a usable response."""


def fetch_year(year: int, client: httpx.Client) -> bytes:
    """Return the raw response holding every published day of ``year``.

    The whole calendar year is always requested. For the current year the
    service simply stops at the last published day, so the same request works
    for a backfill and for a daily run.
    """
    body = _ENVELOPE.format(namespace=NAMESPACE, year=year).encode("utf-8")
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{NAMESPACE}{OPERATION}"',
    }
    response = client.post(SERVICE_URL, content=body, headers=headers)
    # The service reports SOAP faults with HTTP 500, so this covers them too.
    response.raise_for_status()
    return response.content


def parse_rates(xml: bytes) -> list[dict[str, str | None]]:
    """Turn a response into one record per day.

    Values are kept exactly as the service wrote them, as text. Converting
    dates and numbers is the job of the silver layer.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ParseError as error:
        raise BanguatError(f"response is not well-formed XML: {error}") from error

    result = root.find(f".//{{{NAMESPACE}}}{OPERATION}Result")
    if result is None:
        raise BanguatError(f"response has no {OPERATION}Result element")

    rows = [
        {field: var.findtext(f"{{{NAMESPACE}}}{field}") for field in FIELDS}
        for var in result.iter(f"{{{NAMESPACE}}}Var")
    ]

    # The service reports how many records it sent. A mismatch means the
    # response was cut short or its structure changed.
    declared = result.findtext(f"{{{NAMESPACE}}}TotalItems")
    if declared is None or not declared.isdigit() or int(declared) != len(rows):
        raise BanguatError(
            f"response declares {declared!r} records but contains {len(rows)}"
        )
    return rows
