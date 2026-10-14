"""Builds small budget execution workbooks for the tests. Every value is invented."""

from pathlib import Path

from openpyxl import Workbook

from quetzal_ingestion.minfin import COLUMNS


def line(number: int, year: int = 2026, devengado: float = 1500.5) -> list:
    """One budget line with numbers stored as numbers, as in the real workbooks."""
    values = {
        "id": number,
        "ejercicio": year,
        "codigoEntidad": 11130099,
        "entidad": "MINISTERIO DE EJEMPLO",
        "codigoRenglon": 122,
        "renglon": "Impresión, encuadernación y reproducción",
        "asignado": 2000,
        "modificado": -150.25,
        "vigente": 1849.75,
        "devengado": devengado,
    }
    return [
        values.get(column, 0 if column.startswith("codigo") else "N/A")
        for column in COLUMNS
    ]


def write_workbook(path: Path, lines: list[list], header=COLUMNS) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Datos"
    sheet.append(list(header))
    for values in lines:
        sheet.append(values)
    workbook.save(path)
    return path
