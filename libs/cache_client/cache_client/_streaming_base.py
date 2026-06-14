"""StreamingCacheClient — shared base for filecache and vidcache.

Both services expose identical route paths under the ``/cache`` prefix for
reads/deletes, and ``/upload`` + ``/download`` for writes.  All shared logic
lives here; service-specific subclasses add aliases and any unique methods.
"""
from __future__ import annotations

import os
from typing import IO, Iterator, Optional

import httpx

from ._base import BaseCacheClient
from ._stream import _StreamContext


class StreamingCacheClient(BaseCacheClient):
    """Client base for streaming cache services (filecache, vidcache).

    Route contract (both filecache and vidcache implement this layout):

    - ``POST /upload/init``
    - ``POST /upload/{upload_id}``
    - ``POST /download``
    - ``GET  /cache/{hash}``          — raw bytes, supports Range header
    - ``GET  /cache/meta/{hash}``
    - ``GET  /cache/resolve``
    - ``GET  /cache/lookup``
    - ``GET  /cache/search``
    - ``DELETE /cache/{hash}``
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        super().__init__(base_url, timeout)
        self._chunk_size = chunk_size

    # ------------------------------------------------------------------ #
    # Write — two-phase upload                                             #
    # ------------------------------------------------------------------ #

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
        """Phase 1: register upload intent and check the URL dedup fast path.

        Returns a dict with:

        - ``status`` — ``"cached"`` / ``"fresh"`` (already stored) or
          ``"pending"`` (proceed with :meth:`upload_stream`)
        - ``hash`` / ``file_path`` — present when not ``"pending"``
        - ``upload_id`` — present when ``status == "pending"``
        """
        payload: dict = {"url": url, "bucket": bucket}
        if filename is not None:
            payload["filename"] = filename
        if prefix is not None:
            payload["prefix"] = prefix
        if meta is not None:
            payload["meta"] = meta
        if content_hash is not None:
            payload["content_hash"] = content_hash
        resp = self._http.post("/upload/init", json=payload)
        resp.raise_for_status()
        return resp.json()

    def upload_stream(
        self,
        upload_id: str,
        stream: "IO[bytes] | Iterator[bytes]",
    ) -> dict:
        """Phase 2: stream raw bytes to the server for an active upload session.

        *stream* can be any file-like object or bytes iterator.
        Returns ``{"status", "hash", "file_path", "size_bytes"}``.
        """
        def _iter(src: "IO[bytes] | Iterator[bytes]"):
            if hasattr(src, "read"):
                while True:
                    chunk = src.read(self._chunk_size)
                    if not chunk:
                        break
                    yield chunk
            else:
                yield from src

        resp = self._http.post(
            f"/upload/{upload_id}",
            content=_iter(stream),
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()
        return resp.json()

    def ingest_from_url(
        self,
        url: str,
        bucket: str,
        *,
        filename: Optional[str] = None,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        headers: Optional[dict] = None,
        cookies: Optional[dict] = None,
    ) -> dict:
        """Download *url* client-side and stream directly into the cache.

        Bytes flow: source server → this process (one chunk at a time) →
        cache service.  Nothing is written to disk locally.

        Phase 1 (URL dedup check) runs first; if the URL is already cached
        the download is skipped entirely.
        """
        init = self.upload_init(
            url, bucket, filename=filename, prefix=prefix, meta=meta
        )
        if init["status"] in ("cached", "fresh"):
            return init

        upload_id = init["upload_id"]

        def _download_iter():
            with httpx.stream(
                "GET",
                url,
                headers=headers or {},
                cookies=cookies or {},
                follow_redirects=True,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()
                yield from response.iter_bytes(self._chunk_size)

        return self.upload_stream(upload_id, _download_iter())

    def server_download(
        self,
        url: str,
        bucket: str,
        *,
        filename: Optional[str] = None,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        cookies: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """Ask the server to download *url* via its request_auth permit system.

        Use this when you want domain-level rate limiting managed server-side.
        """
        payload: dict = {"url": url, "bucket": bucket}
        if filename is not None:
            payload["filename"] = filename
        if prefix is not None:
            payload["prefix"] = prefix
        if meta is not None:
            payload["meta"] = meta
        if cookies is not None:
            payload["cookies"] = cookies
        if headers is not None:
            payload["headers"] = headers
        resp = self._http.post("/download", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete(self, content_hash: str) -> None:
        """Delete a cached entry and all its URL aliases by content hash."""
        resp = self._http.delete(f"/cache/{content_hash}")
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def resolve(self, url: str) -> Optional[dict]:
        """Resolve a source URL to its content hash entry.

        Returns ``{"hash", "url"}`` or ``None`` if the URL is not cached.
        """
        resp = self._http.get("/cache/resolve", params={"url": url})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_meta(self, content_hash: str) -> Optional[dict]:
        """Retrieve full metadata for a stored entry by content hash.

        Returns ``None`` if not found.
        """
        resp = self._http.get(f"/cache/meta/{content_hash}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def lookup(
        self,
        url: str,
        *,
        max_age: Optional[int] = None,
        version: Optional[str] = None,
    ) -> Optional[dict]:
        """Look up a cached entry by URL with optional freshness constraints.

        Parameters
        ----------
        max_age:
            Return ``None`` when the cached entry's ``retrieved_at`` is older
            than this many seconds.  Mutually exclusive with *version*.
        version:
            Return the entry with this exact content hash.
            Mutually exclusive with *max_age*.
        """
        if max_age is not None and version is not None:
            raise ValueError("max_age and version are mutually exclusive")
        params: dict = {"url": url}
        if max_age is not None:
            params["max_age"] = max_age
        if version is not None:
            params["version"] = version
        resp = self._http.get("/cache/lookup", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search(self, url_contains: str, bucket: str = "default") -> list[dict]:
        """Return metadata for all entries whose URL contains *url_contains*."""
        resp = self._http.get(
            "/cache/search",
            params={"url_contains": url_contains, "bucket": bucket},
        )
        resp.raise_for_status()
        return resp.json()

    def get_bytes(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> bytes:
        """Download a stored entry as raw bytes.

        Parameters
        ----------
        byte_range:
            Optional ``(start, end)`` inclusive byte range.
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        resp = self._http.get(f"/cache/{content_hash}", headers=headers)
        resp.raise_for_status()
        return resp.content

    def stream_content(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> _StreamContext:
        """Stream a stored entry as an iterable of byte chunks.

        Returns a context manager::

            with client.stream_content(hash) as chunks:
                for chunk in chunks:
                    file.write(chunk)
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        return _StreamContext(
            f"{self._base}/cache/{content_hash}",
            headers=headers,
            timeout=self._timeout,
            chunk_size=self._chunk_size,
        )

    def download_to_file(
        self,
        content_hash: str,
        dest: "str | os.PathLike[str]",
        byte_range: Optional[tuple[int, int]] = None,
    ) -> int:
        """Download a stored entry directly to a local path.

        Returns the number of bytes written.
        """
        written = 0
        with self.stream_content(content_hash, byte_range=byte_range) as chunks:
            with open(dest, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
                    written += len(chunk)
        return written
