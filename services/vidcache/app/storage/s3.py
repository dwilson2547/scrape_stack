from __future__ import annotations

import io
from typing import IO, Any

import boto3
from botocore.exceptions import ClientError


class _StreamingBodyReader(io.RawIOBase):
    """Adapts a boto3 StreamingBody to the IO[bytes] protocol."""

    def __init__(self, body: Any) -> None:
        self._body = body

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self._body.close()
        super().close()


class S3VideoStore:
    """S3-compatible video store (works with AWS S3 and MinIO).

    Layout key::

        <prefix>/<hash[:2]>/<hash[2:4]>/<hash>.mp4

    The S3 *bucket* parameter maps directly to an S3 bucket name; buckets
    must already exist before use.

    Files below *multipart_threshold_mb* are uploaded via a single PUT;
    larger files use multipart upload with *multipart_part_size_mb* parts.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        multipart_threshold_mb: int = 100,
        multipart_part_size_mb: int = 64,
    ) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._threshold = multipart_threshold_mb * 1024 * 1024
        self._part_size = multipart_part_size_mb * 1024 * 1024

    def _key(self, prefix: str, hash: str, ext: str = ".mp4") -> str:
        shard = f"{hash[:2]}/{hash[2:4]}/{hash}{ext}"
        return f"{prefix}/{shard}" if prefix else shard

    def exists(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> bool:
        try:
            self._client.head_object(Bucket=bucket, Key=self._key(prefix, hash, ext))
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    def put(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        stream: IO[bytes],
        size: int | None = None,
        ext: str = ".mp4",
    ) -> str:
        key = self._key(prefix, hash, ext)
        if size is not None and size >= self._threshold:
            self._multipart_upload(bucket, key, stream)
        else:
            self._client.put_object(Bucket=bucket, Key=key, Body=stream)
        return f"{bucket}/{key}"

    def _multipart_upload(self, bucket: str, key: str, stream: IO[bytes]) -> None:
        resp = self._client.create_multipart_upload(Bucket=bucket, Key=key)
        upload_id: str = resp["UploadId"]
        parts: list[dict[str, Any]] = []
        part_number = 1
        try:
            while True:
                chunk = stream.read(self._part_size)
                if not chunk:
                    break
                part = self._client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": part["ETag"]})
                part_number += 1
            self._client.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            self._client.abort_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id
            )
            raise

    def get(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        byte_range: tuple[int, int] | None = None,
        ext: str = ".mp4",
    ) -> IO[bytes]:
        key = self._key(prefix, hash, ext)
        kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if byte_range is not None:
            start, end = byte_range
            kwargs["Range"] = f"bytes={start}-{end}"
        resp = self._client.get_object(**kwargs)
        return _StreamingBodyReader(resp["Body"])  # type: ignore[return-value]

    def delete(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> None:
        self._client.delete_object(Bucket=bucket, Key=self._key(prefix, hash, ext))

    def get_size(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> int:
        resp = self._client.head_object(Bucket=bucket, Key=self._key(prefix, hash, ext))
        return int(resp["ContentLength"])
