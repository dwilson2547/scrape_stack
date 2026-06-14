"""ImgCacheClient — client for the imgcache service.

Routes use the ``/cache`` prefix (consistent with all other cache services).
Multipart form-data upload is used for image ingestion;
the service handles perceptual hashing server-side.
"""
from __future__ import annotations

from typing import Optional

import blake3

from ._base import BaseCacheClient


def _content_hash(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


class ImgCacheClient(BaseCacheClient):
    """Python client for the imgcache REST API.

    Usage::

        from cache_client import ImgCacheClient

        with ImgCacheClient("http://localhost:8010") as client:
            entry = client.store(url="https://…/img.jpg", file_bytes=img_bytes, client_name="my_scraper")
            raw = client.get_bytes(entry["hash"])
    """

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def store(
        self,
        url: str,
        file_bytes: bytes,
        client_name: str,
        bucket: str = "default",
        filename: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> dict:
        """Upload image bytes and cache the entry. Returns cache entry metadata."""
        data: dict = {
            "url": url,
            "client_name": client_name,
            "bucket": bucket,
            "content_hash": _content_hash(file_bytes),
        }
        if prefix is not None:
            data["prefix"] = prefix
        fname = filename or "image"
        resp = self._http.post(
            "/cache",
            data=data,
            files={"file": (fname, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    def delete(self, content_hash: str, bucket: str = "default") -> None:
        """Delete a cached image and its URL aliases."""
        resp = self._http.delete(f"/cache/{content_hash}", params={"bucket": bucket})
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def get_bytes(self, content_hash: str, bucket: str = "default") -> bytes:
        """Download raw image bytes by content hash."""
        resp = self._http.get(f"/cache/{content_hash}", params={"bucket": bucket})
        resp.raise_for_status()
        return resp.content

    def get_meta(self, content_hash: str, bucket: str = "default") -> Optional[dict]:
        """Retrieve metadata for a stored image. Returns ``None`` if not found."""
        resp = self._http.get(f"/cache/meta/{content_hash}", params={"bucket": bucket})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def lookup(
        self,
        url: str,
        bucket: Optional[str] = None,
    ) -> Optional[dict]:
        """Look up a cached image by source URL. Returns ``None`` if not found."""
        params: dict = {"url": url}
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._http.get("/cache/lookup", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search(
        self,
        url_contains: str,
        bucket: Optional[str] = None,
    ) -> list[dict]:
        """Return metadata for images whose source URL contains *url_contains*."""
        params: dict = {"url_contains": url_contains}
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._http.get("/cache/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def similar(
        self,
        perceptual_hash: str,
        max_hamming_distance: int = 4,
        bucket: Optional[str] = None,
    ) -> list[dict]:
        """Return images whose perceptual hash is within *max_hamming_distance*."""
        params: dict = {
            "perceptual_hash": perceptual_hash,
            "max_hamming_distance": max_hamming_distance,
        }
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._http.get("/cache/similar", params=params)
        resp.raise_for_status()
        return resp.json()

    def serve_url(self, content_hash: str, bucket: str = "default") -> str:
        """Return the full URL for the ``/serve/{hash}`` endpoint."""
        return f"{self._base}/cache/serve/{content_hash}?bucket={bucket}"
