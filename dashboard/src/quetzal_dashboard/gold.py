"""Read-only access to the gold layer.

The dashboard opens one in-memory DuckDB database, attaches the DuckLake
catalog of prod gold read-only, and gives it a view per published table, so
queries name the tables the same way the dbt models and the documentation
do. Nothing is copied: each query reads the Parquet files of the current
version of gold.main, the last one that passed every test.
"""

import os

import duckdb

# The gold tables the dashboard reads, from gold.main. The exposure `quetzal_dashboard` in
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


def create_s3_secret(con: duckdb.DuckDBPyConnection) -> None:
    """Tell DuckDB how to reach the object store, from the environment.

    S3_ENDPOINT_URL is set for an S3-compatible store and left out for AWS
    S3. The key pair is set as a pair or not at all: without it DuckDB finds
    credentials the standard AWS way, such as the IAM role of the container.
    """
    options: dict[str, object] = {"region": _required("S3_REGION")}
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint:
        # DuckDB expects host:port here and the scheme as a separate flag. A
        # store reached through a plain hostname needs path-style addresses.
        options["endpoint"] = endpoint.removeprefix("https://").removeprefix("http://")
        options["use_ssl"] = endpoint.startswith("https://")
        options["url_style"] = "path"
    key_id = os.environ.get("S3_ACCESS_KEY_ID")
    secret = os.environ.get("S3_SECRET_ACCESS_KEY")
    if bool(key_id) != bool(secret):
        raise RuntimeError("set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither")
    if key_id:
        provider = "config"
        options["key_id"] = key_id
        options["secret"] = secret
    else:
        # Given at all, even empty, a key would override what the chain finds.
        provider = "credential_chain"
    # Values are passed as parameters, so the key pair is never part of a SQL
    # string that could end up in a log.
    fields = "".join(f", {name} ${name}" for name in options)
    con.execute(f"create secret s3 (type s3, provider {provider}{fields})", options)


def create_catalog_secret(con: duckdb.DuckDBPyConnection) -> None:
    """Tell DuckDB how to log in to the DuckLake catalog, from the environment.

    The login can only read the prod gold catalog. The password is passed as
    a parameter, so it is never part of a SQL string that could be logged.
    """
    options: dict[str, object] = {
        "host": _required("LAKE_CATALOG_HOST"),
        "port": int(os.environ.get("LAKE_CATALOG_PORT", "5432")),
        "user": _required("LAKE_CATALOG_USER"),
        "password": _required("LAKE_CATALOG_PASSWORD"),
    }
    fields = ", ".join(f"{name} ${name}" for name in options)
    # Unnamed, so DuckLake uses it to reach the catalog without being told.
    con.execute(f"create secret (type postgres, {fields})", options)


def connect() -> duckdb.DuckDBPyConnection:
    """Open a connection whose views read the published gold tables."""
    con = duckdb.connect()
    for extension in ("httpfs", "ducklake", "postgres"):
        con.load_extension(extension)
    create_s3_secret(con)
    create_catalog_secret(con)
    # Read-only: the catalog login could not write anyway, and DuckDB then
    # never tries to.
    con.execute(
        f"attach 'ducklake:postgres:dbname={_required('LAKE_GOLD_CATALOG')}'"
        " as gold (read_only)"
    )
    for table in TABLES:
        con.execute(f"create view {table} as select * from gold.main.{table}")
    return con
