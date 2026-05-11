"""Integration tests for vidcache through the cluster ingress."""

import io

import pytest

from .conftest import GIF_1x1, RUN_ID, VIDCACHE_URL, VidCacheClient

TEST_URL = f"https://integration-test.scrapestack.local/vidcache/{RUN_ID}/test.gif"
BUCKET = "default"


@pytest.fixture(scope="module")
def stored(vidcache):
    init = vidcache.upload_init(url=TEST_URL, bucket=BUCKET)
    if init["status"] == "pending":
        result = vidcache.upload_stream(init["upload_id"], io.BytesIO(GIF_1x1))
    else:
        result = init
    yield result
    try:
        vidcache.delete(result["hash"])
    except Exception:
        pass


def test_health():
    with VidCacheClient(VIDCACHE_URL) as c:
        resp = c._http.get("/health")
        assert resp.status_code == 200


def test_upload(stored):
    assert "hash" in stored


def test_upload_init_dedup(vidcache, stored):
    # Second init for the same URL should return cached/fresh, not pending.
    init = vidcache.upload_init(url=TEST_URL, bucket=BUCKET)
    assert init["status"] in ("cached", "fresh")


def test_get_bytes(vidcache, stored):
    data = vidcache.get_bytes(stored["hash"])
    assert data == GIF_1x1


def test_get_meta(vidcache, stored):
    meta = vidcache.get_meta(stored["hash"])
    assert meta is not None
    assert TEST_URL in meta["aliases"]


def test_lookup(vidcache, stored):
    result = vidcache.lookup(TEST_URL)
    assert result is not None
    assert result["hash"] == stored["hash"]


def test_resolve(vidcache, stored):
    result = vidcache.resolve(TEST_URL)
    assert result is not None
    assert result["hash"] == stored["hash"]


def test_search(vidcache, stored):
    results = vidcache.search(f"vidcache/{RUN_ID}")
    assert any(r["url"] == TEST_URL for r in results)


def test_stream_content(vidcache, stored):
    chunks = []
    with vidcache.stream_content(stored["hash"]) as stream:
        for chunk in stream:
            chunks.append(chunk)
    assert b"".join(chunks) == GIF_1x1


def test_delete(vidcache):
    url = f"{TEST_URL}/delete-me.gif"
    init = vidcache.upload_init(url=url, bucket=BUCKET)
    if init["status"] == "pending":
        result = vidcache.upload_stream(init["upload_id"], io.BytesIO(GIF_1x1))
    else:
        result = init
    vidcache.delete(result["hash"])
    assert vidcache.get_meta(result["hash"]) is None
