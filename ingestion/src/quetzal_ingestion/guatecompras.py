"""Client for the open contracting data published by Guatecompras.

Guatecompras publishes one file per month, holding the contracting processes
whose tender was published in that month. Each file is a zip with a single
JSON document in the Open Contracting Data Standard (OCDS): a record package,
whose ``records`` array has one element per contracting process.
"""

import codecs
import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

import httpx

SERVICE_URL = "https://ocds.guatecompras.gt/file"

_RECORDS_START = re.compile(r'"records"\s*:\s*\[')
_SEPARATORS = " \t\r\n,"


class GuatecomprasError(Exception):
    """The service answered with something that is not a usable monthly file."""


@dataclass(frozen=True, order=True)
class Month:
    year: int
    month: int

    @classmethod
    def parse(cls, text: str) -> "Month":
        match = re.fullmatch(r"(\d{4})-(\d{2})", text)
        if not match or not 1 <= int(match[2]) <= 12:
            raise ValueError(f"not a month in YYYY-MM form: {text!r}")
        return cls(int(match[1]), int(match[2]))

    def next(self) -> "Month":
        return (
            Month(self.year + 1, 1)
            if self.month == 12
            else Month(self.year, self.month + 1)
        )

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}"


# The service has no files before this month (checked on 2026-10-13).
FIRST_MONTH = Month(2020, 1)


def months_between(first: Month, last: Month) -> list[Month]:
    months = []
    current = first
    while current <= last:
        months.append(current)
        current = current.next()
    return months


def fetch_checksum(month: Month, client: httpx.Client) -> str:
    """Return the SHA-256 the service publishes for the month's JSON file."""
    response = client.get(f"{SERVICE_URL}/sha/{month.year}/{month.month}")
    response.raise_for_status()
    checksum = response.text.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise GuatecomprasError(
            f"checksum for {month} is not a SHA-256: {checksum[:80]!r}"
        )
    return checksum


def fetch_month(month: Month, client: httpx.Client) -> bytes:
    """Return the month's zip file, byte for byte."""
    response = client.get(f"{SERVICE_URL}/json/{month.year}/{month.month}")
    response.raise_for_status()
    return response.content


def open_json(archive: bytes) -> BinaryIO:
    """Open the single JSON document inside a monthly zip, as a byte stream."""
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as error:
        raise GuatecomprasError(f"file is not a zip: {error}") from error
    names = zip_file.namelist()
    if len(names) != 1 or not names[0].endswith(".json"):
        raise GuatecomprasError(f"expected one JSON file in the zip, found {names}")
    return zip_file.open(names[0])


def iter_records(
    document: BinaryIO, *, chunk_size: int = 1 << 20
) -> Iterator[tuple[dict, str]]:
    """Yield every record of an OCDS record package as ``(parsed, text)``.

    The document is read in chunks and never held in memory as a whole: a
    month is hundreds of megabytes of JSON. ``text`` is the record exactly as
    it is written in the file, so it can be stored without re-encoding it.
    """
    decoder = json.JSONDecoder()
    to_text = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    position = None  # Index of the next unread character, once the array is found.

    while True:
        chunk = document.read(chunk_size)
        buffer += to_text.decode(chunk, final=not chunk)

        if position is None:
            start = _RECORDS_START.search(buffer)
            if start:
                position = start.end()
            elif not chunk:
                raise GuatecomprasError("document has no records array")
            else:
                continue

        while True:
            while position < len(buffer) and buffer[position] in _SEPARATORS:
                position += 1
            if position == len(buffer):
                break
            if buffer[position] == "]":
                return
            try:
                record, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                # The record continues in the next chunk.
                break
            yield record, buffer[position:end]
            position = end

        if not chunk:
            raise GuatecomprasError(
                "document is cut off in the middle of the records array"
            )
        buffer = buffer[position:]
        position = 0
