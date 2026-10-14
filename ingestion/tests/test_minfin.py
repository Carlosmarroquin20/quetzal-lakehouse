from datetime import date

import minfin_samples
import pytest

from quetzal_ingestion import minfin
from quetzal_ingestion.minfin import MinfinError


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (11130006.0, "11130006"),
        (1031341.15, "1031341.15"),
        (-150.25, "-150.25"),
        (0.1 + 0.2, "0.30000000000000004"),
        (7, "7"),
        ("SERVICIOS PERSONALES", "SERVICIOS PERSONALES"),
        (date(2026, 10, 5), "2026-10-05"),
        (None, None),
        ("", None),
    ],
)
def test_cell_text_keeps_every_value(value, text):
    assert minfin.cell_text(value) == text


def test_read_rows_returns_each_line_as_text(tmp_path):
    path = minfin_samples.write_workbook(
        tmp_path / "budget.xlsx", [minfin_samples.line(1), minfin_samples.line(2)]
    )

    rows = list(minfin.read_rows(path))

    assert len(rows) == 2
    first = dict(zip(minfin.COLUMNS, rows[0], strict=True))
    assert first["ejercicio"] == "2026"
    assert first["codigoEntidad"] == "11130099"
    assert first["renglon"] == "Impresión, encuadernación y reproducción"
    assert first["modificado"] == "-150.25"
    assert first["devengado"] == "1500.5"


def test_read_rows_rejects_a_changed_header(tmp_path):
    header = [*minfin.COLUMNS[:-1], "pagadoTotal"]
    path = minfin_samples.write_workbook(tmp_path / "budget.xlsx", [], header=header)

    with pytest.raises(
        MinfinError, match=r"missing: \['pagado'\], unexpected: \['pagadoTotal'\]"
    ):
        list(minfin.read_rows(path))


def test_read_rows_rejects_a_file_that_is_not_a_workbook(tmp_path):
    path = tmp_path / "budget.xlsx"
    path.write_text("<html>Just a moment...</html>", encoding="utf-8")

    with pytest.raises(MinfinError, match="not a readable workbook"):
        list(minfin.read_rows(path))
