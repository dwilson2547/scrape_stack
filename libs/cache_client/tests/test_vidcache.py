"""Tests for VidCacheClient."""
import io
import pytest
import respx
import httpx

from cache_client.vidcache import VidCacheClient

BASE = "http://vidcache"


@respx.mock
def test_server_download():
    respx.post(f"{BASE}/download").mock(
        return_value=httpx.Response(200, json={"status": "ok", "hash": "vid1", "file_path": "/data/vid1.mp4"})
    )
    with VidCacheClient(BASE) as c:
        result = c.server_download("https://cdn.example.com/clip.mp4", "raw", filename="clip.mp4")
    assert result["hash"] == "vid1"


@respx.mock
def test_upload_init_no_filename():
    """vidcache upload_init works without filename kwarg."""
    respx.post(f"{BASE}/upload/init").mock(
        return_value=httpx.Response(200, json={"status": "pending", "upload_id": "v-uid-1"})
    )
    with VidCacheClient(BASE) as c:
        result = c.upload_init("https://example.com/clip.mp4", "raw")
    assert result["upload_id"] == "v-uid-1"


@respx.mock
def test_get_meta():
    respx.get(f"{BASE}/cache/meta/vid1").mock(
        return_value=httpx.Response(200, json={"hash": "vid1", "url": "https://cdn.example.com/clip.mp4"})
    )
    with VidCacheClient(BASE) as c:
        meta = c.get_meta("vid1")
    assert meta["hash"] == "vid1"


@respx.mock
def test_get_meta_none_on_404():
    respx.get(f"{BASE}/cache/meta/nope").mock(return_value=httpx.Response(404))
    with VidCacheClient(BASE) as c:
        result = c.get_meta("nope")
    assert result is None


@respx.mock
def test_delete_ok():
    respx.delete(f"{BASE}/cache/vid1").mock(return_value=httpx.Response(200))
    with VidCacheClient(BASE) as c:
        c.delete("vid1")


def test_stream_video_alias():
    """stream_video() is an alias for stream_content()."""
    from cache_client._stream import _StreamContext
    with VidCacheClient(BASE) as c:
        ctx = c.stream_video("vid1")
    assert isinstance(ctx, _StreamContext)
