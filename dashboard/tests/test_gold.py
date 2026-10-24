"""How the dashboard reaches the object store, for a local store and for AWS."""

import duckdb
import pytest

from quetzal_dashboard.gold import create_s3_secret

NAMES = (
    "S3_ENDPOINT_URL", "S3_REGION", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
)


@pytest.fixture
def env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return lambda **values: [monkeypatch.setenv(k, v) for k, v in values.items()]


def secret_of(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    (text,) = con.execute("select secret_string from duckdb_secrets()").fetchone()
    return dict(part.split("=", 1) for part in text.split(";"))


@pytest.fixture
def con():
    con = duckdb.connect()
    # The image installs the extension at build time; a test machine may not
    # have it yet. Installing an extension that is already there is a no-op.
    con.install_extension("httpfs")
    con.load_extension("httpfs")
    return con


def test_a_local_store_uses_its_endpoint_and_key_pair(env, con):
    env(S3_ENDPOINT_URL="http://storage:8333", S3_REGION="us-east-1",
        S3_ACCESS_KEY_ID="local-key", S3_SECRET_ACCESS_KEY="local-secret")

    create_s3_secret(con)

    secret = secret_of(con)
    assert secret["provider"] == "config"
    assert secret["endpoint"] == "storage:8333"
    assert secret["use_ssl"] == "false"
    assert secret["url_style"] == "path"
    assert secret["key_id"] == "local-key"


def test_aws_takes_credentials_from_the_standard_chain(env, con):
    # What the chain would find on AWS, for example from a task role.
    env(S3_REGION="us-east-1", AWS_ACCESS_KEY_ID="role-key",
        AWS_SECRET_ACCESS_KEY="role-secret", AWS_SESSION_TOKEN="role-token")

    create_s3_secret(con)

    secret = secret_of(con)
    assert secret["provider"] == "credential_chain"
    assert secret["key_id"] == "role-key"
    assert secret["endpoint"] == "s3.amazonaws.com"


def test_half_a_key_pair_is_rejected(env, con):
    env(S3_REGION="us-east-1", S3_ACCESS_KEY_ID="local-key")

    with pytest.raises(RuntimeError, match="both"):
        create_s3_secret(con)


def test_the_catalog_login_comes_from_the_environment(monkeypatch, con):
    for name, value in {
        "LAKE_CATALOG_HOST": "catalog",
        "LAKE_CATALOG_USER": "lake_dashboard",
        "LAKE_CATALOG_PASSWORD": "reader-password",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LAKE_CATALOG_PORT", raising=False)
    con.install_extension("postgres")
    con.load_extension("postgres")

    from quetzal_dashboard.gold import create_catalog_secret

    create_catalog_secret(con)

    (text,) = con.execute(
        "select secret_string from duckdb_secrets() where type = 'postgres'"
    ).fetchone()
    secret = dict(part.partition("=")[::2] for part in text.split(";"))
    assert secret["host"] == "catalog"
    assert secret["user"] == "lake_dashboard"
    assert secret["port"] == "5432"
    # DuckDB never shows the password back.
    assert secret["password"] == "redacted"
    assert "reader-password" not in text


def test_a_missing_catalog_password_is_refused(monkeypatch, con):
    monkeypatch.setenv("LAKE_CATALOG_HOST", "catalog")
    monkeypatch.setenv("LAKE_CATALOG_USER", "lake_dashboard")
    monkeypatch.delenv("LAKE_CATALOG_PASSWORD", raising=False)

    from quetzal_dashboard.gold import create_catalog_secret

    with pytest.raises(RuntimeError, match="LAKE_CATALOG_PASSWORD"):
        create_catalog_secret(con)
