"""Read-only access to the gold layer.

The same approach as the dashboard: an in-memory DuckDB database with a view
per gold table over the Parquet file dbt wrote, so queries name the tables
the way the dbt models do. The code is repeated rather than shared because
the two run as separate images with separate key pairs, and neither should
depend on the other's package.
"""

import os

import duckdb

# The gold tables the digest reads. The exposure `daily_digest` in
# transform/models/exposures.yml lists the same tables, so the dbt lineage
# graph shows what a change to them would affect here.
TABLES = (
    "dim_date",
    "dim_currency",
    "dim_buyer",
    "dim_supplier",
    "dim_procurement_method",
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


def connect() -> duckdb.DuckDBPyConnection:
    """Open a connection whose views read gold from the object store."""
    bucket = _required("S3_BUCKET_GOLD")

    con = duckdb.connect()
    con.load_extension("httpfs")
    create_s3_secret(con)
    for table in TABLES:
        con.execute(
            f"create view {table} as "
            f"select * from read_parquet('s3://{bucket}/{table}/{table}.parquet')"
        )
    return con
