import pytest

from quetzal_ingestion.storage import StorageSettings, create_s3_client

LOCAL = {
    "S3_ENDPOINT_URL": "http://storage:8333",
    "S3_REGION": "us-east-1",
    "S3_ACCESS_KEY_ID": "key",
    "S3_SECRET_ACCESS_KEY": "secret",
    "S3_BUCKET_BRONZE": "bronze",
}


@pytest.fixture
def env(monkeypatch):
    for name in LOCAL:
        monkeypatch.delenv(name, raising=False)

    def set_env(values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return set_env


def test_a_local_store_takes_its_endpoint_and_key_pair(env):
    env(LOCAL)

    settings = StorageSettings.from_env()

    assert settings.endpoint_url == "http://storage:8333"
    assert settings.access_key_id == "key"
    assert create_s3_client(settings).meta.config.s3["addressing_style"] == "path"


def test_aws_needs_neither_an_endpoint_nor_keys(env):
    env({"S3_REGION": "us-east-1", "S3_BUCKET_BRONZE": "bronze"})

    settings = StorageSettings.from_env()

    assert settings.endpoint_url is None
    assert settings.access_key_id is None
    assert settings.secret_access_key is None
    client = create_s3_client(settings)
    assert client.meta.endpoint_url == "https://s3.amazonaws.com"
    assert client.meta.config.s3["addressing_style"] == "auto"


def test_half_a_key_pair_is_rejected(env):
    env({**LOCAL, "S3_SECRET_ACCESS_KEY": ""})

    with pytest.raises(RuntimeError, match="both"):
        StorageSettings.from_env()


def test_the_bucket_is_still_required(env):
    env({**LOCAL, "S3_BUCKET_BRONZE": ""})

    with pytest.raises(RuntimeError, match="S3_BUCKET_BRONZE"):
        StorageSettings.from_env()
