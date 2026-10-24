"""How the digest logs in to the DuckLake catalog of gold."""

import duckdb
import pytest


@pytest.fixture
def con():
    con = duckdb.connect()
    con.install_extension("httpfs")
    con.load_extension("httpfs")
    return con


def test_the_catalog_login_comes_from_the_environment(monkeypatch, con):
    for name, value in {
        "LAKE_CATALOG_HOST": "catalog",
        "LAKE_CATALOG_USER": "lake_notifications",
        "LAKE_CATALOG_PASSWORD": "reader-password",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LAKE_CATALOG_PORT", raising=False)
    con.install_extension("postgres")
    con.load_extension("postgres")

    from quetzal_notifications.gold import create_catalog_secret

    create_catalog_secret(con)

    (text,) = con.execute(
        "select secret_string from duckdb_secrets() where type = 'postgres'"
    ).fetchone()
    secret = dict(part.partition("=")[::2] for part in text.split(";"))
    assert secret["host"] == "catalog"
    assert secret["user"] == "lake_notifications"
    assert secret["port"] == "5432"
    # DuckDB never shows the password back.
    assert secret["password"] == "redacted"
    assert "reader-password" not in text


def test_a_missing_catalog_password_is_refused(monkeypatch, con):
    monkeypatch.setenv("LAKE_CATALOG_HOST", "catalog")
    monkeypatch.setenv("LAKE_CATALOG_USER", "lake_notifications")
    monkeypatch.delenv("LAKE_CATALOG_PASSWORD", raising=False)

    from quetzal_notifications.gold import create_catalog_secret

    with pytest.raises(RuntimeError, match="LAKE_CATALOG_PASSWORD"):
        create_catalog_secret(con)
