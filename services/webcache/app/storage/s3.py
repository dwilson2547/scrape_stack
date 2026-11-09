import boto3
from botocore.exceptions import ClientError

from ..config import settings
from .base import BaseStorage


class S3Storage(BaseStorage):
    def __init__(self) -> None:
        kwargs: dict = {
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
            "region_name": settings.s3_region,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.s3_bucket

    def _key(self, bucket: str, content_hash: str, prefix: str | None = None) -> str:
        parts = [bucket]
        if prefix:
            parts.append(prefix)
        parts.append(f"{content_hash}.lz4")
        return "/".join(parts)

    def write(self, bucket: str, content_hash: str, compressed_data: bytes, prefix: str | None = None) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(bucket, content_hash, prefix),
            Body=compressed_data,
        )

    def read(self, bucket: str, content_hash: str, prefix: str | None = None) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=self._key(bucket, content_hash, prefix)
            )
            return response["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"No S3 object for {bucket}/{content_hash}") from exc
            raise

    def delete(self, bucket: str, content_hash: str, prefix: str | None = None) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._key(bucket, content_hash, prefix))

    def exists(self, bucket: str, content_hash: str, prefix: str | None = None) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(bucket, content_hash, prefix))
            return True
        except ClientError:
            return False
