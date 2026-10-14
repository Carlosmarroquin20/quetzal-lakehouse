"""Builds small OCDS record packages for the tests.

Every value is invented. Real Guatecompras files contain personal data and
must not be copied into the repository.
"""

import hashlib
import io
import json
import zipfile


def record(
    number: int, month: str = "2026-09", title: str = "Señal y conversión"
) -> dict:
    ocid = f"ocds-xqjsxa-{number}"
    return {
        "ocid": ocid,
        "releases": [
            {"url": f"https://example.test/release/{number}", "tag": ["tender"]}
        ],
        "compiledRelease": {
            "ocid": ocid,
            "tender": {"id": f"GT-NOG-{number}", "title": title},
            "dataSegmentation": {"id": month},
        },
    }


def package(records: list[dict]) -> bytes:
    """A record package as the source writes it: compact JSON, UTF-8."""
    document = {
        "uri": "https://example.test/file/json/2026/9",
        "version": "1.1",
        "publisher": {"name": "Example publisher"},
        "records": records,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def archive(document: bytes, name: str = "2026-09_Guatecompras.json") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(name, document)
    return buffer.getvalue()


def checksum(document: bytes) -> str:
    return hashlib.sha256(document).hexdigest()
