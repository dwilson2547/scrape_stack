"""Tests for the server-side download endpoint (POST /download).

Uses respx to mock outbound httpx calls so the server never hits the real network.
"""

from __future__ import annotations

import app.request_auth as request_auth_module
import httpx
import pytest
import respx

from tests.conftest import FakeRequestAuthClient

FILE_BYTES = b"Downloaded file content from the internet" * 50
FILE_URL = "https://files.example.com/report.pdf"
FILE_NAME = "report.pdf"
BUCKET = "downloads"


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #

class _TrackingPermit:
    """Permit that records the status code passed to release()."""

    def __init__(self):
        self.released_with: int | None = None

    def set_status(self, code: int) -> None:
        pass

    def release(self, code: int | None = None) -> None:
        self.released_with = code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()


class TrackingRequestAuthClient:
    """Fake client that tracks permit release status codes."""

    def __init__(self):
        self.last_permit: _TrackingPermit | None = None

    def acquire(self, domain: str) -> _TrackingPermit:
        self.last_permit = _TrackingPermit()
        return self.last_permit

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------- #
# Tests                                                                    #
# ---------------------------------------------------------------------- #

@respx.mock
def test_server_download_new_file(client):
    respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=FILE_BYTES))

    resp = client.post("/download", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == FILE_NAME
    assert data["size_bytes"] == len(FILE_BYTES)
    assert data["mime_type"] == "application/pdf"
    assert FILE_URL in data["aliases"]
    assert "hash" in data


@respx.mock
def test_server_download_returns_cached_without_permit(client):
    """If the URL is already cached, no permit should be acquired."""
    tracking = TrackingRequestAuthClient()
    request_auth_module.override_client(tracking)

    try:
        # First: upload the file via two-phase upload
        init = client.post("/upload/init", json={
            "url": FILE_URL,
            "bucket": BUCKET,
            "filename": FILE_NAME,
        }).json()
        client.post(
            f"/upload/{init['upload_id']}",
            content=FILE_BYTES,
            headers={"Content-Type": "application/octet-stream"},
        )

        # Now server_download should hit cache — no HTTP call, no permit
        resp = client.post("/download", json={
            "url": FILE_URL,
            "bucket": BUCKET,
            "filename": FILE_NAME,
        })
        assert resp.status_code == 200
        assert tracking.last_permit is None  # permit was never acquired
    finally:
        request_auth_module.override_client(FakeRequestAuthClient())


@respx.mock
def test_server_download_releases_permit_with_200(client):
    tracking = TrackingRequestAuthClient()
    request_auth_module.override_client(tracking)

    try:
        respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=FILE_BYTES))

        resp = client.post("/download", json={
            "url": FILE_URL,
            "bucket": BUCKET,
            "filename": FILE_NAME,
        })
        assert resp.status_code == 200
        assert tracking.last_permit is not None
        assert tracking.last_permit.released_with == 200
    finally:
        request_auth_module.override_client(FakeRequestAuthClient())


@respx.mock
def test_server_download_releases_permit_on_404(client):
    tracking = TrackingRequestAuthClient()
    request_auth_module.override_client(tracking)

    try:
        respx.get(FILE_URL).mock(return_value=httpx.Response(404))

        resp = client.post("/download", json={
            "url": FILE_URL,
            "bucket": BUCKET,
            "filename": FILE_NAME,
        })
        assert resp.status_code == 502
        assert tracking.last_permit is not None
        assert tracking.last_permit.released_with == 404
    finally:
        request_auth_module.override_client(FakeRequestAuthClient())


@respx.mock
def test_server_download_with_cookies_and_headers(client):
    """Verify cookies and headers are forwarded in the outbound request."""
    route = respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=FILE_BYTES))

    resp = client.post("/download", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
        "cookies": {"session": "abc123"},
        "headers": {"X-Custom-Header": "test-value"},
    })
    assert resp.status_code == 200
    sent_request = route.calls.last.request
    assert "abc123" in sent_request.headers.get("cookie", "")
    assert sent_request.headers.get("x-custom-header") == "test-value"


@respx.mock
def test_server_download_deduplication(client):
    """Uploading the same content via server_download twice returns duplicate."""
    respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=FILE_BYTES))
    alt_url = "https://files.example.com/report-copy.pdf"
    respx.get(alt_url).mock(return_value=httpx.Response(200, content=FILE_BYTES))

    r1 = client.post("/download", json={"url": FILE_URL, "bucket": BUCKET, "filename": FILE_NAME}).json()
    r2 = client.post("/download", json={"url": alt_url, "bucket": BUCKET, "filename": FILE_NAME}).json()

    assert r1["hash"] == r2["hash"]


def test_server_download_unavailable_without_auth(client):
    """Returns 503 when request_auth client is not configured."""
    request_auth_module.override_client(None)
    try:
        resp = client.post("/download", json={
            "url": FILE_URL,
            "bucket": BUCKET,
            "filename": FILE_NAME,
        })
        assert resp.status_code == 503
    finally:
        request_auth_module.override_client(FakeRequestAuthClient())
