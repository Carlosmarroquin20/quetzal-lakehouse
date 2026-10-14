"""Access to the object store that holds the lakehouse layers."""

import os
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class StorageSettings:
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str
    bronze_bucket: str

    @classmethod
    def from_env(cls) -> "StorageSettings":
        names = {
            "endpoint_url": "S3_ENDPOINT_URL",
            "region": "S3_REGION",
            "access_key_id": "S3_ACCESS_KEY_ID",
            "secret_access_key": "S3_SECRET_ACCESS_KEY",
            "bronze_bucket": "S3_BUCKET_BRONZE",
        }
        missing = [name for name in names.values() if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
        return cls(**{field: os.environ[name] for field, name in names.items()})


def create_s3_client(settings: StorageSettings):
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        # Address buckets as endpoint/bucket rather than bucket.endpoint, which
        # a local store reached through a plain hostname cannot resolve.
        config=Config(s3={"addressing_style": "path"}),
    )


def object_metadata(s3, bucket: str, key: str) -> dict[str, str] | None:
    """Return the user metadata of a stored object, or None if there is no object."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return head.get("Metadata", {})
