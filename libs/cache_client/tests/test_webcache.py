"""Tests for WebCacheClient."""
import pytest
import respx
import httpx

from cache_client.webcache import WebCacheClient

BASE = "http://webcache"


@respx.mock
def test_store_returns_entry():
    respx.post(f"{BASE}/cache").mock(return_value=httpx.Response(200, json={"id": 1, "hash": "abc123"}))
    with WebCacheClient(BASE) as c:
        result = c.store(url="https://example.com", content="<html/>", client_name="test")
    assert result["hash"] == "abc123"


@respx.mock
def test_get_returns_entry():
    respx.get(f"{BASE}/cache").mock(return_value=httpx.Response(200, json={"hash": "abc123", "content": "<html/>"}))
    with WebCacheClient(BASE) as c:
        result = c.get(url="https://example.com")
    assert result is not None
    assert result["hash"] == "abc123"


@respx.mock
def test_get_returns_none_on_404():
    respx.get(f"{BASE}/cache").mock(return_value=httpx.Response(404))
    with WebCacheClient(BASE) as c:
        result = c.get(url="https://example.com")
    assert result is None


@respx.mock
def test_search_returns_list():
    respx.get(f"{BASE}/cache/search").mock(
        return_value=httpx.Response(200, json=[{"hash": "abc123"}])
    )
    with WebCacheClient(BASE) as c:
        results = c.search("example.com")
    assert len(results) == 1


@respx.mock
def test_delete_ok():
    respx.delete(f"{BASE}/cache/abc123").mock(return_value=httpx.Response(200))
    with WebCacheClient(BASE) as c:
        c.delete("abc123")


@respx.mock
def test_render_returns_entry():
    respx.get(f"{BASE}/render").mock(return_value=httpx.Response(200, json={"hash": "r1", "content": "<html/>"}))
    with WebCacheClient(BASE) as c:
        result = c.render(url="https://example.com")
    assert result["hash"] == "r1"


@respx.mock
def test_render_returns_none_on_404():
    respx.get(f"{BASE}/render").mock(return_value=httpx.Response(404))
    with WebCacheClient(BASE) as c:
        result = c.render(url="https://gone.com")
    assert result is None
