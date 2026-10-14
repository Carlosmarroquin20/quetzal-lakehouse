"""Reader for the budget execution workbooks of the Ministerio de Finanzas Públicas.

The ministry publishes, for each fiscal year, a workbook with the execution of
the central government's expenditure budget: one sheet, a header row and one
row per budget line. Its portal does not serve the files to automated
clients, so they are downloaded by hand and read from a landing folder.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from python_calamine import CalamineError, CalamineWorkbook

# Header of the workbooks, in order (the same for 2020 to 2026).
COLUMNS = (
    "id",
    "ejercicio",
    "codigoEntidad",
    "entidad",
    "codigoUnidadEjecutora",
    "unidadEjecutora",
    "codigoPrograma",
    "programa",
    "codigoSubProg",
    "subPrograma",
    "codigoProyecto",
    "proyecto",
    "codigoActividad",
    "actividad",
    "codigoObra",
    "obra",
    "codigoDepto",
    "departamento",
    "codigoMunicipio",
    "municipio",
    "codigoTipoPresupuesto",
    "tipoPresupuesto",
    "codigoGrupoGasto",
    "grupoGasto",
    "codigoSubGrpGasto",
    "subGrupoGasto",
    "codigoRenglon",
    "renglon",
    "codigoEconomico",
    "economico",
    "codigoFuente",
    "fuente",
    "codigoOrganismo",
    "organismo",
    "correlativo",
    "asignado",
    "modificado",
    "vigente",
    "preComprometido",
    "comprometido",
    "devengado",
    "pagado",
)


class MinfinError(Exception):
    """A workbook that is not a budget execution file as the ministry publishes it."""


def cell_text(value) -> str | None:
    """Write a cell as text, without losing anything.

    Workbook cells carry their own types, and numbers come back as floating
    point values. A whole number is written without decimals; any other
    number is written with the shortest digits that read back to the same
    value.
    """
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def read_rows(path: Path) -> Iterator[list[str | None]]:
    """Yield the budget lines of a workbook, every cell as text.

    The header must be exactly the expected one: a renamed, missing or extra
    column means the ministry changed its export, and the file is rejected.
    """
    try:
        sheet = CalamineWorkbook.from_path(str(path)).get_sheet_by_index(0)
    except CalamineError as error:
        raise MinfinError(f"{path.name} is not a readable workbook: {error}") from error
    rows = sheet.iter_rows()
    header = tuple(cell_text(value) for value in next(rows, []))
    if header != COLUMNS:
        missing = [column for column in COLUMNS if column not in header]
        extra = [column for column in header if column not in COLUMNS]
        raise MinfinError(
            f"{path.name} does not have the expected columns"
            f" (missing: {missing}, unexpected: {extra})"
        )
    for row in rows:
        yield [cell_text(value) for value in row]
