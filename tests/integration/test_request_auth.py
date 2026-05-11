"""Integration tests for the request-auth gRPC service.

The gRPC server must be reachable at REQUEST_AUTH_GRPC (default:
request-auth-server.scrapestack.local:9000).  The management API must be
reachable at REQUEST_AUTH_API (default: http://auth.scrapestack.local).

A temporary test domain is created at the start of the module and torn down
at the end, so the test is non-destructive to existing data.
"""

import threading

import pytest

from request_auth_client import RequestAuthClient

from .conftest import REQUEST_AUTH_API, REQUEST_AUTH_GRPC, RUN_ID

TEST_DOMAIN = f"integration-test-{RUN_ID}.local"


@pytest.fixture(scope="module", autouse=True)
def test_domain(auth_api):
    """Create a temporary domain with a pool of 2 and tear it down after the module."""
    resp = auth_api.post("/api/domains", json={"hostname": TEST_DOMAIN, "pool_size": 2})
    assert resp.status_code == 201, f"failed to create test domain: {resp.text}"
    yield resp.json()
    auth_api.delete(f"/api/domains/{TEST_DOMAIN}")


def test_health(auth_api):
    resp = auth_api.get("/health")
    assert resp.status_code == 200


def test_connect():
    client = RequestAuthClient(REQUEST_AUTH_GRPC)
    client.close()


def test_acquire_and_release():
    client = RequestAuthClient(REQUEST_AUTH_GRPC)
    try:
        with client.acquire(TEST_DOMAIN) as permit:
            assert permit is not None
            permit.set_status(200)
    finally:
        client.close()


def test_release_with_error_status():
    client = RequestAuthClient(REQUEST_AUTH_GRPC)
    try:
        with client.acquire(TEST_DOMAIN) as permit:
            permit.set_status(500)
    finally:
        client.close()


def test_concurrent_acquires():
    """Two goroutines should both get permits (pool_size=2)."""
    errors = []
    results = []

    def worker():
        client = RequestAuthClient(REQUEST_AUTH_GRPC)
        try:
            with client.acquire(TEST_DOMAIN) as permit:
                results.append(True)
                permit.set_status(200)
        except Exception as exc:
            errors.append(exc)
        finally:
            client.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent acquire errors: {errors}"
    assert len(results) == 2
