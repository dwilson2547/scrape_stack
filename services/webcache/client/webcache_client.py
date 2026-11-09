import blake3
from typing import Optional

import httpx


def _content_hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


class WebCacheClient:
    """
    Python client for the WebCache REST API.

    Usage::

        from webcache_client import WebCacheClient

        client = WebCacheClient("http://localhost:8000")
        client.store(url="https://example.com", content="<html>…</html>", client_name="my_scraper")
        entry = client.get(url="https://example.com", max_age=3600)
        results = client.search(url_contains="example.com", bucket="mybucket")
        rendered = client.render(url="https://example.com", max_age=7200)
        client.delete(content_hash=entry["content_hash"], bucket="default")
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

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
        payload = {
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
        response = self._http.post("/cache", json=payload)
        response.raise_for_status()
        return response.json()

    def delete(self, content_hash: str, bucket: str = "default") -> None:
        """Delete a cached entry by its content hash."""
        response = self._http.delete(f"/cache/{content_hash}", params={"bucket": bucket})
        response.raise_for_status()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        bucket: str = "default",
        max_age: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Retrieve the most recent cached entry for a URL.

        If max_age (seconds) is given, returns None when the cached entry is older
        than that threshold — the caller should then fetch fresh content and store it.
        Returns the full entry dict (including ``content``) or ``None`` if not found.
        """
        params: dict = {"url": url, "bucket": bucket}
        if max_age is not None:
            params["max_age"] = max_age
        response = self._http.get("/cache", params=params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_by_hash(self, content_hash: str, bucket: str = "default") -> Optional[dict]:
        """Retrieve a cached entry by its content hash. Returns ``None`` if not found."""
        response = self._http.get(f"/cache/{content_hash}", params={"bucket": bucket})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def search(self, url_contains: str, bucket: str = "default") -> list[dict]:
        """
        Return metadata for all cached entries in a bucket whose URL contains ``url_contains``.

        Content is not included — call ``get`` or ``get_by_hash`` to retrieve the full page.
        """
        response = self._http.get(
            "/cache/search", params={"url_contains": url_contains, "bucket": bucket}
        )
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(
        self,
        url: str,
        bucket: str = "default",
        max_age: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Return a browser-rendered page with cookies and request metadata.

        Checks the cache first; calls the server's browserless integration if the cache
        is empty or older than max_age (seconds). Returns a dict with ``content``,
        ``cookies``, ``response_metadata``, and standard cache entry fields.
        Returns ``None`` on 404.
        """
        params: dict = {"url": url, "bucket": bucket}
        if max_age is not None:
            params["max_age"] = max_age
        response = self._http.get("/render", params=params, timeout=120.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def post_render_metadata(
        self,
        url: str,
        cookies: Optional[list] = None,
        response_metadata: Optional[dict] = None,
        bucket: str = "default",
    ) -> dict:
        """
        Submit cookies and response metadata for a URL+bucket without triggering a render.
        Use this when the client performed the rendering itself.
        """
        payload = {"url": url, "bucket": bucket}
        if cookies is not None:
            payload["cookies"] = cookies
        if response_metadata is not None:
            payload["response_metadata"] = response_metadata
        response = self._http.post("/render/metadata", json=payload)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def health(self) -> dict:
        response = self._http.get("/health")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
