from __future__ import annotations

import os
from typing import IO, Iterator, Optional

import httpx


class VidCacheClient:
    """Python client for the vidcache REST API.

    Usage::

        from vidcache_client import VidCacheClient

        client = VidCacheClient("http://localhost:8020")

        # Ingest a video — client downloads with its own auth, streams to cache
        result = client.ingest_from_url(
            url="https://example.com/video/abc123",
            bucket="videos",
            prefix="archive",
            meta={"title": "Cool video"},
            headers={"Authorization": "Bearer token"},
            cookies={"session": "abc"},
        )
        print(result["hash"])    # BLAKE3 content hash
        print(result["status"])  # "new" | "duplicate" | "cached"

        # Or drive the two phases manually:
        init = client.upload_init("https://example.com/video/abc123", bucket="videos")
        if init["status"] == "pending":
            with open("local.mp4", "rb") as f:
                result = client.upload_stream(init["upload_id"], f)

        # Resolve a URL to its hash
        entry = client.resolve("https://example.com/video/abc123")

        # Retrieve metadata
        meta = client.get_meta(entry["hash"])

        # Stream video bytes
        with client.stream_video(entry["hash"]) as stream:
            with open("video.mp4", "wb") as f:
                for chunk in stream:
                    f.write(chunk)

        # Delete
        client.delete(entry["hash"])

        client.close()  # or use as a context manager
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        """
        Parameters
        ----------
        base_url:
            Base URL of the vidcache service, e.g. ``http://localhost:8020``.
        timeout:
            Request timeout in seconds.  Video ingest can take a while, so
            the default is 5 minutes rather than the usual 30 s.
        chunk_size:
            Byte chunk size used when streaming downloads and uploads
            (default 1 MB).
        """
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._chunk_size = chunk_size
        self._http = httpx.Client(base_url=self._base, timeout=timeout)

    # ------------------------------------------------------------------ #
    # Write — two-phase upload                                             #
    # ------------------------------------------------------------------ #

    def upload_init(
        self,
        url: str,
        bucket: str,
        prefix: str = "",
        meta: Optional[dict] = None,
    ) -> dict:
        """Phase 1: register upload metadata and check the URL dedup fast path.

        Returns a dict with:

        - ``status`` — ``"cached"`` (already stored, no upload needed) or
          ``"pending"`` (proceed with :meth:`upload_stream`)
        - ``hash`` / ``file_path`` — present when ``status == "cached"``
        - ``upload_id`` — present when ``status == "pending"``
        """
        payload: dict = {"url": url, "bucket": bucket, "prefix": prefix}
        if meta is not None:
            payload["meta"] = meta
        resp = self._http.post("/upload/init", json=payload)
        resp.raise_for_status()
        return resp.json()

    def upload_stream(
        self,
        upload_id: str,
        stream: "IO[bytes] | Iterator[bytes]",
    ) -> dict:
        """Phase 2: stream raw bytes to the server for an active upload session.

        *stream* can be any file-like object (``read()`` is called repeatedly)
        or any iterator of ``bytes`` chunks.

        Returns the same result dict as :meth:`ingest_from_url`.
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
        prefix: str = "",
        meta: Optional[dict] = None,
        *,
        headers: Optional[dict] = None,
        cookies: Optional[dict] = None,
    ) -> dict:
        """Download *url* (with optional auth) and stream directly to the cache.

        Bytes flow: source server → this process (one chunk at a time) →
        vidcache server.  Nothing is written to disk locally.

        Phase 1 (URL dedup check) is performed first; if the URL is already
        cached the download is skipped entirely.

        Parameters
        ----------
        url:
            Source URL of the video to ingest.
        bucket:
            Storage bucket name (e.g. ``"videos"``).
        prefix:
            Optional path prefix inside the bucket.
        meta:
            Optional dict of arbitrary metadata.
        headers:
            Extra HTTP headers forwarded to the source server
            (e.g. ``{"Authorization": "Bearer token"}``).
        cookies:
            Cookies forwarded to the source server.
        """
        init = self.upload_init(url, bucket=bucket, prefix=prefix, meta=meta)
        if init["status"] == "cached":
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

    def delete(self, content_hash: str) -> None:
        """Delete a cached video and all its URL aliases by content hash."""
        resp = self._http.delete(f"/video/{content_hash}")
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def resolve(self, url: str) -> Optional[dict]:
        """Resolve a source URL to its content hash entry.

        Returns a dict with ``hash`` and ``url``, or ``None`` if the URL has
        never been ingested.
        """
        resp = self._http.get("/resolve", params={"url": url})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_meta(self, content_hash: str) -> Optional[dict]:
        """Retrieve metadata for a stored video by its content hash.

        Returns a dict including ``hash``, ``size_bytes``, ``duration_s``,
        ``first_seen``, ``aliases`` (list of all known source URLs), and any
        client-supplied ``meta``.  Returns ``None`` if not found.
        """
        resp = self._http.get(f"/meta/{content_hash}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_bytes(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> bytes:
        """Download a stored video as raw bytes.

        Parameters
        ----------
        content_hash:
            BLAKE3 content hash of the video.
        byte_range:
            Optional ``(start, end)`` inclusive byte range for partial
            retrieval.  Maps to an HTTP ``Range: bytes=start-end`` request.
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        resp = self._http.get(f"/video/{content_hash}", headers=headers)
        resp.raise_for_status()
        return resp.content

    def stream_video(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> "_StreamContext":
        """Stream a stored video as an iterable of byte chunks.

        Returns a context manager that yields chunks.  The underlying HTTP
        connection is closed automatically on exit::

            with client.stream_video(hash) as chunks:
                for chunk in chunks:
                    file.write(chunk)

        Parameters
        ----------
        byte_range:
            Optional ``(start, end)`` inclusive byte range.
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        url = f"{self._base}/video/{content_hash}"
        return _StreamContext(url, headers=headers, timeout=self._timeout, chunk_size=self._chunk_size)

    def download_to_file(
        self,
        content_hash: str,
        dest: "str | os.PathLike[str]",
        byte_range: Optional[tuple[int, int]] = None,
    ) -> int:
        """Download a stored video directly to a local file path.

        Parameters
        ----------
        dest:
            Filesystem path to write the video to.
        byte_range:
            Optional ``(start, int)`` inclusive byte range for partial
            retrieval.

        Returns
        -------
        Number of bytes written.
        """
        written = 0
        with self.stream_video(content_hash, byte_range=byte_range) as chunks:
            with open(dest, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
                    written += len(chunk)
        return written

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> "VidCacheClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class _StreamContext:
    """Context manager wrapping an httpx streaming response."""

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
        self._response: Optional[httpx.Response] = None
        self._client: Optional[httpx.Client] = None
        self._stream_ctx = None  # keep alive to prevent GC closing the stream

    def __enter__(self) -> "Iterator[bytes]":
        self._client = httpx.Client(timeout=self._timeout)
        self._stream_ctx = self._client.stream("GET", self._url, headers=self._headers)
        self._response = self._stream_ctx.__enter__()
        self._response.raise_for_status()
        return self._response.iter_bytes(chunk_size=self._chunk_size)  # type: ignore[return-value]

    def __exit__(self, *args: object) -> None:
        if self._stream_ctx is not None:
            try:
                self._stream_ctx.__exit__(*args)
            except Exception:
                pass
        if self._client is not None:
            self._client.close()
