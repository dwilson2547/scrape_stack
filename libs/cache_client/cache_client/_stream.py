"""_StreamContext — reusable context manager for streaming HTTP responses."""
from __future__ import annotations

from typing import Iterator, Optional

import httpx


class _StreamContext:
    """Context manager that wraps an httpx streaming GET and yields byte chunks.

    Usage::

        with _StreamContext(url, headers={}, timeout=300.0, chunk_size=1024*1024) as chunks:
            for chunk in chunks:
                file.write(chunk)
    """

    def __init__(
        self,
        url: str,
        headers: dict,
        timeout: float,
        chunk_size: int,
    ) -> None:
        self._url = url
        self._headers = headers
        self._timeout = timeout
        self._chunk_size = chunk_size
        self._client: Optional[httpx.Client] = None
        self._stream_ctx = None

    def __enter__(self) -> Iterator[bytes]:
        self._client = httpx.Client(timeout=self._timeout)
        self._stream_ctx = self._client.stream("GET", self._url, headers=self._headers)
        response = self._stream_ctx.__enter__()
        response.raise_for_status()
        return response.iter_bytes(chunk_size=self._chunk_size)  # type: ignore[return-value]

    def __exit__(self, *args: object) -> None:
        if self._stream_ctx is not None:
            try:
                self._stream_ctx.__exit__(*args)
            except Exception:
                pass
        if self._client is not None:
            self._client.close()
