import httpx
from typing import Optional


class ImgCacheClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=timeout)

    def store(self, url: str, file_bytes: bytes, client_name: str,
              bucket: str = "", filename: Optional[str] = None) -> dict:
        data: dict = {"url": url, "client_name": client_name, "bucket": bucket}
        fname = filename or "image"
        resp = self._client.post(
            "/images",
            data=data,
            files={"file": (fname, file_bytes)},
        )
        resp.raise_for_status()
        return resp.json()

    def get_bytes(self, content_hash: str, bucket: str = "") -> bytes:
        resp = self._client.get(f"/images/{content_hash}", params={"bucket": bucket})
        resp.raise_for_status()
        return resp.content

    def get_meta(self, content_hash: str, bucket: str = "") -> Optional[dict]:
        resp = self._client.get(f"/images/meta/{content_hash}", params={"bucket": bucket})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def lookup(self, url: str, bucket: Optional[str] = None) -> Optional[dict]:
        params: dict = {"url": url}
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._client.get("/images/lookup", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def search(self, url_contains: str, bucket: Optional[str] = None) -> list:
        params: dict = {"url_contains": url_contains}
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._client.get("/images/search", params=params)
        resp.raise_for_status()
        return resp.json()

    def similar(self, perceptual_hash: str, max_hamming_distance: int = 4,
                bucket: Optional[str] = None) -> list:
        params: dict = {"perceptual_hash": perceptual_hash, "max_hamming_distance": max_hamming_distance}
        if bucket is not None:
            params["bucket"] = bucket
        resp = self._client.get("/images/similar", params=params)
        resp.raise_for_status()
        return resp.json()

    def delete(self, content_hash: str, bucket: str = "") -> None:
        resp = self._client.delete(f"/images/{content_hash}", params={"bucket": bucket})
        resp.raise_for_status()

    def serve_url(self, content_hash: str, bucket: str = "") -> str:
        url = f"{self._base}/serve/{content_hash}"
        if bucket:
            url += f"?bucket={bucket}"
        return url

    def health(self) -> dict:
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._client.close()
