"""Access to the object store that holds the lakehouse layers."""

import os
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class StorageSettings:
    region: str
    bronze_bucket: str
    # Set for an S3-compatible store; left out for AWS S3 itself.
    endpoint_url: str | None = None
    # Set as a pair, or both left out. Without them boto3 finds credentials
    # the standard AWS way, for example the IAM role of the container it runs
    # in, so no long-lived key has to be handed to the job.
    access_key_id: str | None = None
    secret_access_key: str | None = None

    @classmethod
    def from_env(cls) -> "StorageSettings":
        required = {"region": "S3_REGION", "bronze_bucket": "S3_BUCKET_BRONZE"}
        missing = [name for name in required.values() if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
        key_id = os.environ.get("S3_ACCESS_KEY_ID") or None
        secret = os.environ.get("S3_SECRET_ACCESS_KEY") or None
        if (key_id is None) != (secret is None):
            raise RuntimeError(
                "set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither"
            )
        return cls(
            **{field: os.environ[name] for field, name in required.items()},
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            access_key_id=key_id,
            secret_access_key=secret,
        )


def create_s3_client(settings: StorageSettings):
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        # A store reached through a plain hostname cannot resolve
        # bucket.endpoint, so buckets are addressed as endpoint/bucket there.
        # AWS S3 itself keeps its default addressing.
        config=Config(
            s3={"addressing_style": "path" if settings.endpoint_url else "auto"}
        ),
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
