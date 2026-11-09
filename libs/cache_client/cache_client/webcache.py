"""WebCacheClient — client for the webcache service."""
from __future__ import annotations

from typing import Optional

import blake3

from ._base import BaseCacheClient


def _content_hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


class WebCacheClient(BaseCacheClient):
    """Python client for the webcache REST API.

    Usage::

        from cache_client import WebCacheClient

        with WebCacheClient("http://localhost:8000") as client:
            client.store(url="https://example.com", content="<html>…</html>", client_name="my_scraper")
            entry = client.get(url="https://example.com", max_age=3600)
            rendered = client.render(url="https://example.com", max_age=7200)
    """

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def store(
        self,
        url: str,
        content: str,
        client_name: str,
        bucket: str = "default",
        prefix: Optional[str] = None,
        cookies: Optional[list] = None,
        response_metadata: Optional[dict] = None,
    ) -> dict:
        """Cache a web page as a new version. Returns cache entry metadata."""
        payload: dict = {
            "url": url,
            "content": content,
            "content_hash": _content_hash(content),
            "client_name": client_name,
            "bucket": bucket,
        }
        if prefix is not None:
            payload["prefix"] = prefix
        if cookies is not None:
            payload["cookies"] = cookies
        if response_metadata is not None:
            payload["response_metadata"] = response_metadata
        resp = self._http.post("/cache", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete(self, content_hash: str, bucket: str = "default") -> None:
        """Delete a cached entry by its content hash."""
        resp = self._http.delete(f"/cache/{content_hash}", params={"bucket": bucket})
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def get(
        self,
        url: str,
        bucket: str = "default",
        max_age: Optional[int] = None,
    ) -> Optional[dict]:
        """Retrieve the most recent cached entry for a URL (including content).

        Returns ``None`` when not found or when the entry is older than
        *max_age* seconds.
        """
        params: dict = {"url": url, "bucket": bucket}
        if max_age is not None:
            params["max_age"] = max_age
        resp = self._http.get("/cache", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_by_hash(
        self,
        content_hash: str,
        bucket: str = "default",
    ) -> Optional[dict]:
        """Retrieve a cached entry by its content hash. Returns ``None`` if not found."""
        resp = self._http.get(f"/cache/{content_hash}", params={"bucket": bucket})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search(
        self,
        url_contains: str,
        bucket: str = "default",
    ) -> list[dict]:
        """Return metadata (no content) for entries whose URL contains *url_contains*."""
        resp = self._http.get(
            "/cache/search",
            params={"url_contains": url_contains, "bucket": bucket},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Render                                                               #
    # ------------------------------------------------------------------ #

    def render(
        self,
        url: str,
        bucket: str = "default",
        max_age: Optional[int] = None,
    ) -> Optional[dict]:
        """Return a browser-rendered page, using the cache when fresh.

        Calls the server's browserless integration on a cache miss or when the
        cached entry is older than *max_age* seconds.  Returns a dict with
        ``content``, ``cookies``, ``response_metadata``, and standard cache
        entry fields.  Returns ``None`` on 404.
        """
        params: dict = {"url": url, "bucket": bucket}
        if max_age is not None:
            params["max_age"] = max_age
        resp = self._http.get("/render", params=params, timeout=120.0)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def post_render_metadata(
        self,
        url: str,
        cookies: Optional[list] = None,
        response_metadata: Optional[dict] = None,
        bucket: str = "default",
    ) -> dict:
        """Submit cookies and response metadata for a URL without triggering a render.

        Use this when the client performed rendering itself.
        """
        payload: dict = {"url": url, "bucket": bucket}
        if cookies is not None:
            payload["cookies"] = cookies
        if response_metadata is not None:
            payload["response_metadata"] = response_metadata
        resp = self._http.post("/render/metadata", json=payload)
        resp.raise_for_status()
        return resp.json()
