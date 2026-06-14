"""Tests for FileCacheClient (and implicitly StreamingCacheClient)."""
import io
import pytest
import respx
import httpx

from cache_client.filecache import FileCacheClient

BASE = "http://filecache"


@respx.mock
def test_upload_init_cached():
    respx.post(f"{BASE}/upload/init").mock(
        return_value=httpx.Response(200, json={"status": "cached", "hash": "abc", "file_path": "/data/abc"})
    )
    with FileCacheClient(BASE) as c:
        result = c.upload_init("https://example.com/data.zip", "default", filename="data.zip")
    assert result["status"] == "cached"


@respx.mock
def test_upload_init_pending():
    respx.post(f"{BASE}/upload/init").mock(
        return_value=httpx.Response(200, json={"status": "pending", "upload_id": "uid-1"})
    )
    with FileCacheClient(BASE) as c:
        result = c.upload_init("https://example.com/new.zip", "default")
    assert result["status"] == "pending"
    assert result["upload_id"] == "uid-1"


@respx.mock
def test_upload_stream():
    respx.post(f"{BASE}/upload/uid-1").mock(
        return_value=httpx.Response(200, json={"status": "ok", "hash": "xyz", "file_path": "/data/xyz", "size_bytes": 9})
    )
    with FileCacheClient(BASE) as c:
        result = c.upload_stream("uid-1", io.BytesIO(b"test data"))
    assert result["hash"] == "xyz"


@respx.mock
def test_resolve_returns_none_on_404():
    respx.get(f"{BASE}/cache/resolve").mock(return_value=httpx.Response(404))
    with FileCacheClient(BASE) as c:
        result = c.resolve("https://missing.com/file.zip")
    assert result is None


@respx.mock
def test_get_meta_returns_none_on_404():
    respx.get(f"{BASE}/cache/meta/nope").mock(return_value=httpx.Response(404))
    with FileCacheClient(BASE) as c:
        result = c.get_meta("nope")
    assert result is None


@respx.mock
def test_get_bytes():
    respx.get(f"{BASE}/cache/abc").mock(return_value=httpx.Response(200, content=b"file content"))
    with FileCacheClient(BASE) as c:
        data = c.get_bytes("abc")
    assert data == b"file content"


@respx.mock
def test_lookup_returns_none_on_404():
    respx.get(f"{BASE}/cache/lookup").mock(return_value=httpx.Response(404))
    with FileCacheClient(BASE) as c:
        result = c.lookup("https://missing.com/file.zip")
    assert result is None


@respx.mock
def test_search_returns_list():
    respx.get(f"{BASE}/cache/search").mock(return_value=httpx.Response(200, json=[{"hash": "abc"}]))
    with FileCacheClient(BASE) as c:
        results = c.search("example.com")
    assert len(results) == 1


@respx.mock
def test_delete_ok():
    respx.delete(f"{BASE}/cache/abc").mock(return_value=httpx.Response(200))
    with FileCacheClient(BASE) as c:
        c.delete("abc")


def test_lookup_max_age_version_mutex():
    with FileCacheClient(BASE) as c:
        with pytest.raises(ValueError):
            c.lookup("https://example.com", max_age=60, version="abc")


def test_stream_file_alias():
    """stream_file() returns a _StreamContext (alias for stream_content)."""
    from cache_client._stream import _StreamContext
    with FileCacheClient(BASE) as c:
        ctx = c.stream_file("abc")
    assert isinstance(ctx, _StreamContext)
