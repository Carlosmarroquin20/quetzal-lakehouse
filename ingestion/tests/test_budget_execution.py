import io
from datetime import UTC, datetime

import minfin_samples
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError

from quetzal_ingestion import budget_execution
from quetzal_ingestion.minfin import MinfinError

INGESTED_AT = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class FakeS3:
    """Stands in for the S3 client: a put replaces whatever the key held."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict] = {}
        self.puts = 0

    def put_object(self, *, Bucket, Key, Body, Metadata=None, **_):
        self.objects[Key] = Body
        self.metadata[Key] = Metadata or {}
        self.puts += 1

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"Metadata": self.metadata[Key]}


def load(s3: FakeS3, path, **options) -> bool:
    workbook = budget_execution.read_workbook(path, ingested_at=INGESTED_AT)
    return budget_execution.ingest_workbook(workbook, s3=s3, bucket="bronze", **options)


def test_keys_are_partitioned_by_fiscal_year():
    assert budget_execution.raw_key(2026) == (
        "minfin/central_government_expenditure/raw/year=2026/budget_execution.xlsx"
    )
    assert budget_execution.parquet_key(2026) == (
        "minfin/central_government_expenditure/parquet/year=2026/budget_execution.parquet"
    )


def test_the_fiscal_year_comes_from_the_content_not_the_file_name(tmp_path):
    path = minfin_samples.write_workbook(
        tmp_path / "descarga-2025.xlsx", [minfin_samples.line(1, year=2026)]
    )

    workbook = budget_execution.read_workbook(path, ingested_at=INGESTED_AT)

    assert workbook.year == 2026


def test_a_workbook_is_stored_as_the_original_file_and_text_parquet(tmp_path):
    s3 = FakeS3()
    path = minfin_samples.write_workbook(
        tmp_path / "ejecución 2026.xlsx",
        [minfin_samples.line(1), minfin_samples.line(2)],
    )

    assert load(s3, path) is True

    raw = budget_execution.raw_key(2026)
    assert s3.objects[raw] == path.read_bytes()
    assert s3.metadata[raw]["original-file-name"] == "ejecuci%C3%B3n%202026.xlsx"
    table = pq.read_table(io.BytesIO(s3.objects[budget_execution.parquet_key(2026)]))
    assert table.num_rows == 2
    first = table.slice(0, 1).to_pylist()[0]
    assert first["codigoEntidad"] == "11130099"
    assert first["devengado"] == "1500.5"
    assert first["_source_file"] == raw
    assert first["_ingested_at"] == INGESTED_AT


def test_loading_the_same_file_again_writes_nothing(tmp_path):
    s3 = FakeS3()
    path = minfin_samples.write_workbook(tmp_path / "b.xlsx", [minfin_samples.line(1)])

    load(s3, path)
    puts = s3.puts

    assert load(s3, path) is False
    assert s3.puts == puts


def test_a_newer_file_of_the_same_year_replaces_the_stored_one(tmp_path):
    s3 = FakeS3()
    load(
        s3,
        minfin_samples.write_workbook(tmp_path / "old.xlsx", [minfin_samples.line(1)]),
    )
    newer = minfin_samples.write_workbook(
        tmp_path / "new.xlsx",
        [minfin_samples.line(1, devengado=2000), minfin_samples.line(2)],
    )

    assert load(s3, newer) is True
    assert len(s3.objects) == 2
    table = pq.read_table(io.BytesIO(s3.objects[budget_execution.parquet_key(2026)]))
    assert table.num_rows == 2


def test_force_loads_the_same_file_again(tmp_path):
    s3 = FakeS3()
    path = minfin_samples.write_workbook(tmp_path / "b.xlsx", [minfin_samples.line(1)])

    load(s3, path)

    assert load(s3, path, force=True) is True


def test_a_workbook_mixing_fiscal_years_is_rejected(tmp_path):
    path = minfin_samples.write_workbook(
        tmp_path / "b.xlsx",
        [minfin_samples.line(1, year=2026), minfin_samples.line(2, year=2025)],
    )

    with pytest.raises(MinfinError, match="mixes fiscal years: 2026 and 2025"):
        budget_execution.read_workbook(path, ingested_at=INGESTED_AT)


def test_a_workbook_without_lines_is_rejected(tmp_path):
    path = minfin_samples.write_workbook(tmp_path / "b.xlsx", [])

    with pytest.raises(MinfinError, match="has no budget lines"):
        budget_execution.read_workbook(path, ingested_at=INGESTED_AT)


def test_two_files_of_the_same_year_are_rejected(tmp_path):
    workbooks = [
        budget_execution.read_workbook(
            minfin_samples.write_workbook(tmp_path / name, [minfin_samples.line(1)]),
            ingested_at=INGESTED_AT,
        )
        for name in ("a.xlsx", "b.xlsx")
    ]

    with pytest.raises(
        MinfinError, match=r"more than one file for fiscal year \[2026\]"
    ):
        budget_execution.check_one_file_per_year(workbooks)


def test_landed_files_skips_excel_lock_files(tmp_path):
    for name in ("a.xlsx", "~$a.xlsx", "notes.txt"):
        (tmp_path / name).write_bytes(b"")

    assert [path.name for path in budget_execution.landed_files(tmp_path)] == ["a.xlsx"]
