"""dbt-duckdb plugin that gives SQL models a keyed pseudonymization function.

`pseudonymize(value)` returns the HMAC-SHA256 of the value with a secret key.
The same value always gets the same pseudonym, so rows can still be counted
and joined, but without the key nobody can compute the pseudonym of a given
value. A plain hash would not do: tax numbers are few enough to hash them all
and look the pseudonym up.

The key is read from the PSEUDONYMIZATION_KEY environment variable when the
function is first called. It never appears in SQL, so it is not written to
the compiled models, the logs or the documentation site.
"""

import hashlib
import hmac
import os

import pyarrow as pa
from dbt.adapters.duckdb.plugins import BasePlugin


class Plugin(BasePlugin):
    def configure_connection(self, conn):
        key: bytes | None = None

        def pseudonymize(values: pa.Array) -> pa.Array:
            nonlocal key
            if key is None:
                secret = os.environ.get("PSEUDONYMIZATION_KEY")
                if not secret:
                    raise RuntimeError("PSEUDONYMIZATION_KEY is not set")
                key = secret.encode("utf-8")
            return pa.array(
                [
                    None
                    if value is None
                    else hmac.new(
                        key, value.encode("utf-8"), hashlib.sha256
                    ).hexdigest()
                    for value in values.to_pylist()
                ],
                type=pa.string(),
            )

        # Registered as a vectorized function: DuckDB hands over a batch of
        # values at a time. Called once per row instead, it took about 5 ms a
        # row, which made a fact table of half a million rows take hours.
        conn.create_function(
            "pseudonymize",
            pseudonymize,
            ["VARCHAR"],
            "VARCHAR",
            type="arrow",
            null_handling="special",
        )
