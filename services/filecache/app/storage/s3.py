from __future__ import annotations

from typing import IO

import boto3
import boto3.s3.transfer
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from .base import BaseStorage, make_file_path


class _StreamingBodyReader:
    """Adapts a boto3 StreamingBody to a readable file-like interface."""

    def __init__(self, body) -> None:
        self._body = body

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._body.read()
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()

    def __enter__(self) -> "_StreamingBodyReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class S3Storage(BaseStorage):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str = "us-east-1",
        multipart_threshold_mb: int = 100,
        multipart_part_size_mb: int = 64,
    ) -> None:
        self._bucket = bucket
        self._multipart_threshold = multipart_threshold_mb * 1024 * 1024
        self._multipart_part_size = multipart_part_size_mb * 1024 * 1024
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or None,
            region_name=region_name,
            # Disable checksum validation so Range GETs work against MinIO and
            # older S3-compatible endpoints that don't return object checksums.
            config=BotoConfig(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("404", "NoSuchBucket"):
                raise
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except ClientError as ce:
                if ce.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

    def write(self, bucket: str, prefix: "str | None", content_hash: str, stream: IO[bytes], ext: str) -> str:
        key = make_file_path(bucket, prefix, content_hash, ext)
        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=self._multipart_threshold,
            multipart_chunksize=self._multipart_part_size,
        )
        self._client.upload_fileobj(stream, self._bucket, key, Config=transfer_config)
        return key

    def read(
        self,
        bucket: str,
        prefix: "str | None",
        content_hash: str,
        ext: str,
        byte_range: "tuple[int, int] | None" = None,
    ) -> "_StreamingBodyReader":
        key = make_file_path(bucket, prefix, content_hash, ext)
        kwargs: dict = {"Bucket": self._bucket, "Key": key}
        if byte_range is not None:
            start, end = byte_range
            kwargs["Range"] = f"bytes={start}-{end}"
        resp = self._client.get_object(**kwargs)
        return _StreamingBodyReader(resp["Body"])

    def delete(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> None:
        key = make_file_path(bucket, prefix, content_hash, ext)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> bool:
        key = make_file_path(bucket, prefix, content_hash, ext)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def get_size(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> int:
        key = make_file_path(bucket, prefix, content_hash, ext)
        resp = self._client.head_object(Bucket=self._bucket, Key=key)
        return resp["ContentLength"]
