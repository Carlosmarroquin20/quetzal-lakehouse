"""dbt-duckdb plugin that lets DuckDB log in to the DuckLake catalog.

The catalog of silver and gold is a Postgres database (the `catalog` service).
This plugin creates the Postgres secret DuckDB uses to reach it, from the
environment, before the profile attaches the catalogs. The password is
passed as a parameter, so it never appears in the ATTACH statement or in
anything dbt logs or compiles.

Without LAKE_CATALOG_HOST, as in CI, there is no catalog to log in to: the
profile then attaches local catalogs instead, and this plugin does nothing.
"""

import os

from dbt.adapters.duckdb.plugins import BasePlugin


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


class Plugin(BasePlugin):
    def configure_connection(self, conn):
        host = os.environ.get("LAKE_CATALOG_HOST")
        if not host:
            return
        conn.load_extension("postgres")
        conn.load_extension("ducklake")
        options = {
            "host": host,
            "port": int(os.environ.get("LAKE_CATALOG_PORT", "5432")),
            "user": _required("LAKE_CATALOG_USER"),
            "password": _required("LAKE_CATALOG_PASSWORD"),
        }
        fields = ", ".join(f"{name} ${name}" for name in options)
        # Unnamed, so DuckLake uses it for every catalog on this server.
        conn.execute(f"create or replace secret (type postgres, {fields})", options)
