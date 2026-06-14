"""FileCacheClient — client for the filecache service."""
from __future__ import annotations

from typing import Optional

from ._streaming_base import StreamingCacheClient


class FileCacheClient(StreamingCacheClient):
    """Python client for the filecache REST API.

    Inherits all upload/download/streaming methods from
    :class:`~cache_client._streaming_base.StreamingCacheClient`.

    The ``stream_file`` method is an alias for ``stream_content`` for
    readability in file-handling code.

    Usage::

        from cache_client import FileCacheClient

        with FileCacheClient("http://localhost:8020") as client:
            result = client.ingest_from_url(
                "https://example.com/data.zip",
                bucket="downloads",
                filename="data.zip",
            )
            client.download_to_file(result["hash"], "/local/data.zip")
    """

    def stream_file(self, content_hash: str, byte_range=None):
        """Stream a stored file as chunks — alias for :meth:`stream_content`."""
        return self.stream_content(content_hash, byte_range=byte_range)

    def upload_init(
        self,
        url: str,
        bucket: str,
        *,
        filename: Optional[str] = None,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        content_hash: Optional[str] = None,
    ) -> dict:
        """Phase-1 upload for filecache — includes ``filename`` in the payload."""
        return super().upload_init(
            url,
            bucket,
            filename=filename,
            prefix=prefix,
            meta=meta,
            content_hash=content_hash,
        )
