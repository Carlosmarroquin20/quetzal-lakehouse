"""Read-only access to the gold layer.

The dashboard opens one in-memory DuckDB database and gives it a view per gold
table over the Parquet file dbt wrote, so queries name the tables the same way
the dbt models and the README do. Nothing is copied: each query reads the
files in the bucket, so the dashboard shows what the last dbt build wrote.
"""

import os

import duckdb

# The gold tables the dashboard reads. Each one is a single Parquet file
# under a folder with the table's name. The exposure `quetzal_dashboard` in
# transform/models/exposures.yml lists the same tables, so the dbt lineage
# graph shows what a change to them would affect here.
TABLES = (
    "dim_date",
    "dim_currency",
    "dim_buyer",
    "dim_supplier",
    "dim_procurement_method",
    "dim_entity",
    "fct_exchange_rates",
    "fct_awards",
    "fct_budget_execution",
)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def connect() -> duckdb.DuckDBPyConnection:
    """Open a connection whose views read gold from the object store."""
    endpoint = _required("S3_ENDPOINT_URL")
    bucket = _required("S3_BUCKET_GOLD")

    con = duckdb.connect()
    con.load_extension("httpfs")
    # The key pair is passed as parameters, so it is never part of a SQL
    # string that could end up in a log.
    con.execute(
        """
        create secret gold (
            type s3,
            key_id $key_id,
            secret $secret,
            region $region,
            endpoint $endpoint,
            use_ssl $use_ssl,
            url_style 'path'
        )
        """,
        {
            "key_id": _required("S3_ACCESS_KEY_ID"),
            "secret": _required("S3_SECRET_ACCESS_KEY"),
            "region": _required("S3_REGION"),
            # DuckDB expects host:port here and the scheme as a separate flag.
            "endpoint": endpoint.removeprefix("https://").removeprefix("http://"),
            "use_ssl": endpoint.startswith("https://"),
        },
    )
    for table in TABLES:
        con.execute(
            f"create view {table} as "
            f"select * from read_parquet('s3://{bucket}/{table}/{table}.parquet')"
        )
    return con
