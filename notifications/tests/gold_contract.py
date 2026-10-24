"""Gold's contract, applied to the small gold tables the tests write.

The dbt models of gold declare every column and its type in
transform/models/gold, and a build fails unless gold matches. Rebuilding
the invented tables with those types means the queries are tested against
the types gold publishes, and a column they read that gold does not have
fails here, before it fails against the real gold.
"""

from pathlib import Path

import duckdb
import yaml

GOLD_MODELS = Path(__file__).resolve().parents[2] / "transform" / "models" / "gold"


def gold_contract() -> dict[str, dict[str, str]]:
    """The columns and types of every gold model, in their declared order."""
    contract = {}
    for path in sorted(GOLD_MODELS.glob("*.yml")):
        for model in yaml.safe_load(path.read_text(encoding="utf-8")).get("models", []):
            contract[model["name"]] = {
                column["name"]: column["data_type"] for column in model["columns"]
            }
    if not contract:
        raise RuntimeError(f"no gold models found in {GOLD_MODELS}")
    return contract


def conform_to_contract(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild every table of the connection with the types of the contract.

    Columns a table leaves out are added empty. A table that is not a gold
    model, or a column the model does not have, is refused.
    """
    contract = gold_contract()
    tables = con.execute(
        "select table_name from duckdb_tables() where schema_name = 'main' order by 1"
    ).fetchall()
    for (table,) in tables:
        if table not in contract:
            raise ValueError(f"{table} is not a gold model")
        given = con.execute(
            "select column_name from duckdb_columns()"
            " where schema_name = 'main' and table_name = ?",
            [table],
        ).fetchall()
        unknown = [column for (column,) in given if column not in contract[table]]
        if unknown:
            raise ValueError(f"gold's contract has no column {', '.join(unknown)} in {table}")
        definition = ", ".join(f'"{name}" {type_}' for name, type_ in contract[table].items())
        con.execute(f'alter table "{table}" rename to "{table}__given"')
        con.execute(f'create table "{table}" ({definition})')
        con.execute(f'insert into "{table}" by name select * from "{table}__given"')
        con.execute(f'drop table "{table}__given"')
