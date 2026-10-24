"""The catalog backup job, with pg_dump and S3 replaced so nothing leaves the test."""

from datetime import date
from pathlib import Path

import pytest

from quetzal_backup import catalog_backup
from quetzal_backup.catalog_backup import Settings, back_up, dump_key, expired_keys, pg_dump_command

TODAY = date(2026, 10, 24)

SETTINGS = Settings(
    region="us-east-1",
    bucket="backups",
    catalog_host="catalog",
    catalog_user="lake_backup",
    catalog_password="backup-password",
    catalogs=("lake_silver", "lake_gold"),
    keep_days=14,
)


class FakeS3:
    def __init__(self, keys=()):
        self.objects = {key: b"old" for key in keys}

    def upload_file(self, filename, bucket, key):
        assert bucket == "backups"
        self.objects[key] = Path(filename).read_bytes()

    def list_objects_v2(self, *, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)]}

    def delete_object(self, *, Bucket, Key):
        del self.objects[Key]


def fake_pg_dump(calls):
    def run(command, env, check):
        calls.append((command, env))
        path = Path(command[command.index("--file") + 1])
        path.write_bytes(f"dump of {command[-1]}".encode())

    return run


def test_one_dump_per_catalog_and_day():
    assert dump_key("lake_gold", TODAY) == "catalog/lake_gold/2026-10-24.dump"


def test_dumps_older_than_the_kept_days_expire():
    keys = [dump_key("lake_gold", date(2026, 10, day)) for day in range(1, 25)]

    expired = expired_keys(keys, "lake_gold", TODAY, keep_days=14)

    # 14 days kept, today included: 11 to 24 October.
    assert expired == [dump_key("lake_gold", date(2026, 10, day)) for day in range(1, 11)]


def test_only_dumps_of_the_catalog_are_considered():
    keys = [
        "catalog/lake_silver/2026-01-01.dump",
        "catalog/lake_gold/notes.txt",
        "catalog/lake_gold/not-a-date.dump",
        "catalog/lake_gold/2026-01-01.dump",
    ]

    assert expired_keys(keys, "lake_gold", TODAY, keep_days=14) == [
        "catalog/lake_gold/2026-01-01.dump"
    ]


def test_the_password_never_goes_on_the_command_line(tmp_path):
    command = pg_dump_command(SETTINGS, "lake_gold", tmp_path / "x.dump")

    assert "backup-password" not in " ".join(command)
    assert command[-1] == "lake_gold"
    assert command[command.index("--format") + 1] == "custom"


def test_every_catalog_is_dumped_and_uploaded():
    s3 = FakeS3()
    calls = []

    written = back_up(SETTINGS, s3, TODAY, run=fake_pg_dump(calls))

    assert written == [
        "catalog/lake_silver/2026-10-24.dump",
        "catalog/lake_gold/2026-10-24.dump",
    ]
    assert s3.objects["catalog/lake_gold/2026-10-24.dump"] == b"dump of lake_gold"
    assert all(env["PGPASSWORD"] == "backup-password" for _, env in calls)


def test_expired_dumps_are_deleted_after_the_new_ones_are_written():
    old = dump_key("lake_gold", date(2026, 9, 1))
    recent = dump_key("lake_gold", date(2026, 10, 20))
    s3 = FakeS3([old, recent])

    back_up(SETTINGS, s3, TODAY, run=fake_pg_dump([]))

    assert old not in s3.objects
    assert recent in s3.objects


def test_a_failed_dump_deletes_nothing():
    old = dump_key("lake_gold", date(2026, 9, 1))
    s3 = FakeS3([old])

    def failing_run(command, env, check):
        raise catalog_backup.subprocess.CalledProcessError(1, command)

    with pytest.raises(catalog_backup.subprocess.CalledProcessError):
        back_up(SETTINGS, s3, TODAY, run=failing_run)

    assert old in s3.objects


@pytest.fixture
def env(monkeypatch):
    values = {
        "S3_REGION": "us-east-1",
        "S3_BUCKET_BACKUPS": "backups",
        "LAKE_CATALOG_HOST": "catalog",
        "LAKE_CATALOG_USER": "lake_backup",
        "LAKE_CATALOG_PASSWORD": "backup-password",
        "BACKUP_CATALOGS": "lake_silver, lake_gold",
    }
    for name in (*values, "BACKUP_KEEP_DAYS", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_settings_come_from_the_environment(env):
    settings = Settings.from_env()

    assert settings.catalogs == ("lake_silver", "lake_gold")
    assert settings.keep_days == 14
    assert settings.endpoint_url is None


def test_half_a_key_pair_is_refused(env):
    env.setenv("S3_ACCESS_KEY_ID", "key")

    with pytest.raises(RuntimeError, match="both"):
        Settings.from_env()
