"""Integration tests for webcache through the cluster ingress."""

import pytest

from .conftest import RUN_ID, WEBCACHE_URL, WebCacheClient

TEST_URL = f"https://integration-test.scrapestack.local/webcache/{RUN_ID}"
TEST_CONTENT = f"<html><body>integration test {RUN_ID}</body></html>"
CLIENT_NAME = "integration-test"


@pytest.fixture(scope="module")
def stored(webcache):
    entry = webcache.store(url=TEST_URL, content=TEST_CONTENT, client_name=CLIENT_NAME)
    yield entry
    try:
        webcache.delete(entry["content_hash"])
    except Exception:
        pass


def test_health():
    with WebCacheClient(WEBCACHE_URL) as c:
        resp = c._http.get("/health")
        assert resp.status_code == 200


def test_store(stored):
    assert "content_hash" in stored
    assert stored["url"] == TEST_URL


def test_get_by_url(webcache, stored):
    entry = webcache.get(TEST_URL)
    assert entry is not None
    assert entry["content_hash"] == stored["content_hash"]
    assert TEST_CONTENT in entry["content"]


def test_get_by_hash(webcache, stored):
    entry = webcache.get_by_hash(stored["content_hash"])
    assert entry is not None
    assert entry["url"] == TEST_URL


def test_search(webcache, stored):
    results = webcache.search(f"webcache/{RUN_ID}")
    assert any(r["url"] == TEST_URL for r in results)


def test_delete(webcache):
    # Store a separate entry so deleting it doesn't break other tests.
    url = f"{TEST_URL}/delete-me"
    entry = webcache.store(url=url, content="delete test", client_name=CLIENT_NAME)
    webcache.delete(entry["content_hash"])
    assert webcache.get_by_hash(entry["content_hash"]) is None
