"""Tests for ImgCacheClient."""
import pytest
import respx
import httpx

from cache_client.imgcache import ImgCacheClient

BASE = "http://imgcache"


@respx.mock
def test_store_multipart():
    respx.post(f"{BASE}/images").mock(return_value=httpx.Response(200, json={"hash": "img1"}))
    with ImgCacheClient(BASE) as c:
        result = c.store(url="https://example.com/img.jpg", file_bytes=b"\xff\xd8\xff", client_name="test")
    assert result["hash"] == "img1"


@respx.mock
def test_get_bytes():
    respx.get(f"{BASE}/images/img1").mock(return_value=httpx.Response(200, content=b"\xff\xd8\xff"))
    with ImgCacheClient(BASE) as c:
        data = c.get_bytes("img1")
    assert data == b"\xff\xd8\xff"


@respx.mock
def test_get_meta_returns_none_on_404():
    respx.get(f"{BASE}/images/meta/nope").mock(return_value=httpx.Response(404))
    with ImgCacheClient(BASE) as c:
        result = c.get_meta("nope")
    assert result is None


@respx.mock
def test_lookup_returns_none_on_404():
    respx.get(f"{BASE}/images/lookup").mock(return_value=httpx.Response(404))
    with ImgCacheClient(BASE) as c:
        result = c.lookup("https://missing.com/img.jpg")
    assert result is None


@respx.mock
def test_similar_returns_list():
    respx.get(f"{BASE}/images/similar").mock(return_value=httpx.Response(200, json=[{"hash": "img2"}]))
    with ImgCacheClient(BASE) as c:
        results = c.similar("aabbccdd", max_hamming_distance=2)
    assert len(results) == 1


@respx.mock
def test_delete_ok():
    respx.delete(f"{BASE}/images/img1").mock(return_value=httpx.Response(200))
    with ImgCacheClient(BASE) as c:
        c.delete("img1")


def test_serve_url_format():
    c = ImgCacheClient(BASE)
    url = c.serve_url("img1")
    assert url == f"{BASE}/serve/img1?bucket=default"
    c.close()
