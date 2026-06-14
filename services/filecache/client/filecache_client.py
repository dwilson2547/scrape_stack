"""Python client for the filecache REST API.

Usage::

    from filecache_client import FileCacheClient

    client = FileCacheClient("http://localhost:8030")

    # Two-phase upload — client downloads the file and streams it to the cache
    result = client.ingest_from_url(
        url="https://example.com/report.pdf",
        bucket="documents",
        filename="report.pdf",
        headers={"Authorization": "Bearer token"},
    )
    print(result["hash"])    # BLAKE3 content hash
    print(result["status"])  # "new" | "duplicate"

    # Or drive the two phases manually:
    init = client.upload_init("https://example.com/report.pdf", bucket="documents", filename="report.pdf")
    if init["status"] == "pending":
        with open("local.pdf", "rb") as f:
            result = client.upload_stream(init["upload_id"], f)

    # Ask the server to download the file (uses request_auth internally)
    result = client.server_download(
        url="https://example.com/protected.zip",
        bucket="archives",
        filename="protected.zip",
        cookies={"session": "abc"},
    )

    # Lookup by URL with a freshness constraint
    entry = client.lookup("https://example.com/report.pdf", max_age=86400)

    # Stream file bytes
    with client.stream_file(entry["hash"]) as chunks:
        with open("local_copy.pdf", "wb") as f:
            for chunk in chunks:
                f.write(chunk)

    client.close()  # or use as a context manager
"""

from __future__ import annotations

import os
from typing import IO, Iterator, Optional

import httpx


class FileCacheClient:
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
            Base URL of the filecache service, e.g. ``http://localhost:8030``.
        timeout:
            Request timeout in seconds (default 5 min for large file transfers).
        chunk_size:
            Byte chunk size used when streaming uploads and downloads (default 1 MB).
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
        filename: str,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        content_hash: Optional[str] = None,
    ) -> dict:
        """Phase 1: register upload metadata and check the URL dedup fast path.

        Returns a dict with:

        - ``status`` — ``"cached"`` / ``"fresh"`` (already stored) or ``"pending"``
          (proceed with :meth:`upload_stream`)
        - ``hash`` / ``file_path`` — present when not ``"pending"``
        - ``upload_id`` — present when ``status == "pending"``
        """
        payload: dict = {"url": url, "bucket": bucket, "filename": filename}
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
        filename: str,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        *,
        headers: Optional[dict] = None,
        cookies: Optional[dict] = None,
    ) -> dict:
        """Download *url* (with optional auth) and stream directly to the cache.

        Bytes flow: source server → this process (one chunk at a time) →
        filecache server.  Nothing is written to disk locally.

        Phase 1 (URL dedup check) is performed first; if the URL is already
        cached the download is skipped entirely.
        """
        init = self.upload_init(url, bucket=bucket, filename=filename, prefix=prefix, meta=meta)
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

    # ------------------------------------------------------------------ #
    # Write — server-side download                                         #
    # ------------------------------------------------------------------ #

    def server_download(
        self,
        url: str,
        bucket: str,
        filename: str,
        prefix: Optional[str] = None,
        meta: Optional[dict] = None,
        *,
        cookies: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """Ask the server to download *url* using the request_auth permit system.

        The server acquires a rate-limit permit for the URL's domain, downloads
        the file, and returns the full file metadata record.

        Use this when you want domain-level queuing and rate limiting managed
        server-side (e.g. multiple scrapers hitting the same domain).
        """
        payload: dict = {"url": url, "bucket": bucket, "filename": filename}
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
        """Delete a cached file and all its URL aliases by content hash."""
        resp = self._http.delete(f"/files/{content_hash}")
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def resolve(self, url: str) -> Optional[dict]:
        """Resolve a source URL to its content hash entry.

        Returns ``{"hash", "url"}`` or ``None`` if the URL is not cached.
        """
        resp = self._http.get("/resolve", params={"url": url})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_meta(self, content_hash: str) -> Optional[dict]:
        """Retrieve full metadata for a stored file by its content hash.

        Returns ``None`` if not found.
        """
        resp = self._http.get(f"/meta/{content_hash}")
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
        """Look up a cached file by URL.

        Parameters
        ----------
        url:
            Source URL to look up.
        max_age:
            If given, returns ``None`` when the cached entry's ``retrieved_at``
            is older than this many seconds.  Mutually exclusive with *version*.
        version:
            If given, return the exact file with this content hash (ignoring
            the URL association).  Mutually exclusive with *max_age*.
        """
        if max_age is not None and version is not None:
            raise ValueError("max_age and version are mutually exclusive")
        params: dict = {"url": url}
        if max_age is not None:
            params["max_age"] = max_age
        if version is not None:
            params["version"] = version
        resp = self._http.get("/lookup", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search(self, url_contains: str, bucket: str = "default") -> list[dict]:
        """Return metadata for all entries in *bucket* whose URL contains *url_contains*."""
        resp = self._http.get("/search", params={"url_contains": url_contains, "bucket": bucket})
        resp.raise_for_status()
        return resp.json()

    def get_bytes(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> bytes:
        """Download a stored file as raw bytes.

        Parameters
        ----------
        byte_range:
            Optional ``(start, end)`` inclusive byte range.
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        resp = self._http.get(f"/files/{content_hash}", headers=headers)
        resp.raise_for_status()
        return resp.content

    def stream_file(
        self,
        content_hash: str,
        byte_range: Optional[tuple[int, int]] = None,
    ) -> "_StreamContext":
        """Stream a stored file as an iterable of byte chunks.

        Returns a context manager::

            with client.stream_file(hash) as chunks:
                for chunk in chunks:
                    file.write(chunk)
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        url = f"{self._base}/files/{content_hash}"
        return _StreamContext(url, headers=headers, timeout=self._timeout, chunk_size=self._chunk_size)

    def download_to_file(
        self,
        content_hash: str,
        dest: "str | os.PathLike[str]",
        byte_range: Optional[tuple[int, int]] = None,
    ) -> int:
        """Download a stored file directly to a local path.

        Returns the number of bytes written.
        """
        written = 0
        with self.stream_file(content_hash, byte_range=byte_range) as chunks:
            with open(dest, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
                    written += len(chunk)
        return written

    # ------------------------------------------------------------------ #
    # Misc                                                                 #
    # ------------------------------------------------------------------ #

    def health(self) -> dict:
        resp = self._http.get("/health")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FileCacheClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class _StreamContext:
    """Context manager wrapping an httpx streaming response."""

    def __init__(self, url: str, headers: dict, timeout: float, chunk_size: int) -> None:
        self._url = url
        self._headers = headers
        self._timeout = timeout
        self._chunk_size = chunk_size
        self._client: Optional[httpx.Client] = None
        self._stream_ctx = None

    def __enter__(self) -> "Iterator[bytes]":
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
