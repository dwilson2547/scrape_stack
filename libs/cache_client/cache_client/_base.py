"""BaseCacheClient — shared constructor, health check, and lifecycle for all cache clients."""
from __future__ import annotations

import httpx


class BaseCacheClient:
    """Minimal base shared by every cache service client.

    Provides:
    - ``httpx.Client`` construction
    - ``health()``
    - ``close()`` / context-manager support
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._http = httpx.Client(base_url=self._base, timeout=timeout)

    def health(self) -> dict:
        """Return the service health payload ``{"status": "ok"}``."""
        resp = self._http.get("/health")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> "BaseCacheClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
