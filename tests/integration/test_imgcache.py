"""Integration tests for imgcache through the cluster ingress."""

import pytest

from .conftest import IMGCACHE_URL, PNG_1x1, RUN_ID, ImgCacheClient

TEST_URL = f"https://integration-test.scrapestack.local/imgcache/{RUN_ID}/test.png"
CLIENT_NAME = "integration-test"


@pytest.fixture(scope="module")
def stored(imgcache):
    entry = imgcache.store(
        url=TEST_URL,
        file_bytes=PNG_1x1,
        client_name=CLIENT_NAME,
        filename="test.png",
    )
    yield entry
    try:
        imgcache.delete(entry["hash"])
    except Exception:
        pass


def test_health():
    with ImgCacheClient(IMGCACHE_URL) as c:
        resp = c._http.get("/health")
        assert resp.status_code == 200


def test_store(stored):
    assert "hash" in stored
    assert stored["url"] == TEST_URL


def test_get_bytes(imgcache, stored):
    data = imgcache.get_bytes(stored["hash"])
    assert data == PNG_1x1


def test_get_meta(imgcache, stored):
    meta = imgcache.get_meta(stored["hash"])
    assert meta is not None
    assert meta["url"] == TEST_URL
    assert "perceptual_hash" in meta


def test_lookup(imgcache, stored):
    result = imgcache.lookup(TEST_URL)
    assert result is not None
    assert result["hash"] == stored["hash"]


def test_search(imgcache, stored):
    results = imgcache.search(f"imgcache/{RUN_ID}")
    assert any(r["url"] == TEST_URL for r in results)


def test_similar(imgcache, stored):
    meta = imgcache.get_meta(stored["hash"])
    phash = meta["perceptual_hash"]
    results = imgcache.similar(phash, max_hamming_distance=0)
    assert any(r["hash"] == stored["hash"] for r in results)


def test_delete(imgcache):
    url = f"{TEST_URL}/delete-me.png"
    entry = imgcache.store(url=url, file_bytes=PNG_1x1, client_name=CLIENT_NAME)
    imgcache.delete(entry["hash"])
    assert imgcache.get_meta(entry["hash"]) is None
