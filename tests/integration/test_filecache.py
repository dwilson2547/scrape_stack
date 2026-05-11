"""Integration tests for filecache through the cluster ingress."""

import io

import pytest

from .conftest import FILECACHE_URL, RUN_ID, FileCacheClient

TEST_URL = f"https://integration-test.scrapestack.local/filecache/{RUN_ID}/test.txt"
TEST_CONTENT = f"integration test content {RUN_ID}".encode()
BUCKET = "default"


@pytest.fixture(scope="module")
def stored(filecache):
    init = filecache.upload_init(url=TEST_URL, bucket=BUCKET, filename="test.txt")
    if init["status"] == "pending":
        result = filecache.upload_stream(init["upload_id"], io.BytesIO(TEST_CONTENT))
    else:
        result = init
    yield result
    try:
        filecache.delete(result["hash"])
    except Exception:
        pass


def test_health():
    with FileCacheClient(FILECACHE_URL) as c:
        resp = c._http.get("/health")
        assert resp.status_code == 200


def test_upload(stored):
    assert "hash" in stored


def test_upload_init_dedup(filecache, stored):
    init = filecache.upload_init(url=TEST_URL, bucket=BUCKET, filename="test.txt")
    assert init["status"] in ("cached", "fresh")


def test_get_bytes(filecache, stored):
    data = filecache.get_bytes(stored["hash"])
    assert data == TEST_CONTENT


def test_get_meta(filecache, stored):
    meta = filecache.get_meta(stored["hash"])
    assert meta is not None
    assert TEST_URL in meta["aliases"]


def test_lookup(filecache, stored):
    result = filecache.lookup(TEST_URL)
    assert result is not None
    assert result["hash"] == stored["hash"]


def test_resolve(filecache, stored):
    result = filecache.resolve(TEST_URL)
    assert result is not None
    assert result["hash"] == stored["hash"]


def test_search(filecache, stored):
    results = filecache.search(f"filecache/{RUN_ID}")
    assert any(r["url"] == TEST_URL for r in results)


def test_stream_file(filecache, stored):
    chunks = []
    with filecache.stream_file(stored["hash"]) as stream:
        for chunk in stream:
            chunks.append(chunk)
    assert b"".join(chunks) == TEST_CONTENT


def test_delete(filecache):
    url = f"{TEST_URL}/delete-me.txt"
    init = filecache.upload_init(url=url, bucket=BUCKET, filename="delete-me.txt")
    if init["status"] == "pending":
        result = filecache.upload_stream(init["upload_id"], io.BytesIO(TEST_CONTENT))
    else:
        result = init
    filecache.delete(result["hash"])
    assert filecache.get_meta(result["hash"]) is None
