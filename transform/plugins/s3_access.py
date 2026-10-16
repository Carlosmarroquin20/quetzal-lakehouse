"""dbt-duckdb plugin that tells DuckDB how to reach the object store.

S3_ENDPOINT_URL is set for an S3-compatible store and left out for AWS S3.
The key pair is set as a pair or not at all: without it DuckDB finds
credentials the standard AWS way, such as the IAM role of the container dbt
runs in, so no long-lived key has to be handed to the job.

This is done here and not in profiles.yml because the profile cannot leave a
setting out depending on the environment, and a key given at all, even
empty, overrides what the credential chain finds. The dashboard builds the
same secret in dashboard/src/quetzal_dashboard/gold.py.
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
        conn.load_extension("httpfs")
        options: dict[str, object] = {"region": _required("S3_REGION")}
        endpoint = os.environ.get("S3_ENDPOINT_URL")
        if endpoint:
            # DuckDB expects host:port here and the scheme as a separate flag.
            # A store reached through a plain hostname needs path-style
            # addresses.
            options["endpoint"] = endpoint.removeprefix("https://").removeprefix(
                "http://"
            )
            options["use_ssl"] = endpoint.startswith("https://")
            options["url_style"] = "path"
        key_id = os.environ.get("S3_ACCESS_KEY_ID")
        secret = os.environ.get("S3_SECRET_ACCESS_KEY")
        if bool(key_id) != bool(secret):
            raise RuntimeError(
                "set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither"
            )
        if key_id:
            provider = "config"
            options["key_id"] = key_id
            options["secret"] = secret
        else:
            provider = "credential_chain"
        # Values are passed as parameters, so the key pair never appears in
        # SQL that dbt could log or compile.
        fields = "".join(f", {name} ${name}" for name in options)
        conn.execute(
            f"create or replace secret s3 (type s3, provider {provider}{fields})",
            options,
        )
