"""Tests for BaseCacheClient."""
import pytest
import respx
import httpx

from cache_client._base import BaseCacheClient


@respx.mock
def test_health_ok():
    respx.get("http://test-svc/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    with BaseCacheClient("http://test-svc") as client:
        result = client.health()
    assert result == {"status": "ok"}


@respx.mock
def test_health_error_raises():
    respx.get("http://test-svc/health").mock(return_value=httpx.Response(503))
    client = BaseCacheClient("http://test-svc")
    with pytest.raises(httpx.HTTPStatusError):
        client.health()
    client.close()


def test_context_manager_closes():
    with BaseCacheClient("http://test-svc") as client:
        assert not client._http.is_closed
    assert client._http.is_closed
