"""
API integration tests — run against a local-storage in-memory test app.
"""

import blake3

import pytest


def _hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


def _page(url: str, content: str) -> dict:
    return {
        "url": url,
        "content": content,
        "content_hash": _hash(content),
        "client_name": "test_scraper",
    }


PAGE_A = _page("https://example.com/page-a", "<html><body>Page A content</body></html>")
PAGE_B = _page("https://example.com/page-b?ref=1", "<html><body>Page B content (different)</body></html>")


class TestStoreAndRetrieve:
    def test_store_returns_201(self, client):
        response = client.post("/cache", json=PAGE_A)
        assert response.status_code == 201
        data = response.json()
        assert data["url"] == PAGE_A["url"]
        assert data["client_name"] == PAGE_A["client_name"]
        assert data["content_hash"] == PAGE_A["content_hash"]

    def test_store_same_url_same_hash_returns_200(self, client):
        client.post("/cache", json=PAGE_A)
        response = client.post("/cache", json=PAGE_A)
        assert response.status_code == 200

    def test_store_same_url_different_content_returns_201(self, client):
        client.post("/cache", json=PAGE_A)
        updated = _page(PAGE_A["url"], "<html><body>Updated content</body></html>")
        response = client.post("/cache", json=updated)
        assert response.status_code == 201

    def test_store_hash_mismatch_returns_422(self, client):
        bad = {**PAGE_A, "content_hash": "a" * 64}
        response = client.post("/cache", json=bad)
        assert response.status_code == 422

    def test_get_by_url_returns_content(self, client):
        client.post("/cache", json=PAGE_A)
        response = client.get("/cache", params={"url": PAGE_A["url"]})
        assert response.status_code == 200
        assert response.json()["content"] == PAGE_A["content"]

    def test_get_by_url_404(self, client):
        response = client.get("/cache", params={"url": "https://notcached.example.com"})
        assert response.status_code == 404

    def test_get_by_hash(self, client):
        store_resp = client.post("/cache", json=PAGE_A)
        content_hash = store_resp.json()["content_hash"]
        response = client.get(f"/cache/{content_hash}")
        assert response.status_code == 200
        assert response.json()["content"] == PAGE_A["content"]

    def test_get_by_hash_404(self, client):
        response = client.get("/cache/" + "a" * 64)
        assert response.status_code == 404

    def test_store_sets_retrieved_at(self, client):
        resp = client.post("/cache", json=PAGE_A)
        assert resp.json().get("retrieved_at") is not None

    def test_duplicate_bumps_retrieved_at(self, client):
        client.post("/cache", json=PAGE_A)
        r1 = client.post("/cache", json=PAGE_A)
        assert r1.status_code == 200
        assert r1.json().get("retrieved_at") is not None


class TestLookup:
    def test_lookup_by_url(self, client):
        client.post("/cache", json=PAGE_A)
        response = client.get("/cache/lookup", params={"url": PAGE_A["url"]})
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == PAGE_A["url"]
        assert "content" not in data

    def test_lookup_miss_404(self, client):
        response = client.get("/cache/lookup", params={"url": "https://missing.example.com"})
        assert response.status_code == 404

    def test_lookup_by_version(self, client):
        resp = client.post("/cache", json=PAGE_A)
        version = resp.json()["content_hash"]
        response = client.get("/cache/lookup", params={"url": PAGE_A["url"], "version": version})
        assert response.status_code == 200

    def test_lookup_version_miss(self, client):
        response = client.get("/cache/lookup", params={"url": PAGE_A["url"], "version": "b" * 64})
        assert response.status_code == 404

    def test_lookup_max_age_and_version_mutually_exclusive(self, client):
        resp = client.post("/cache", json=PAGE_A)
        version = resp.json()["content_hash"]
        response = client.get(
            "/cache/lookup",
            params={"url": PAGE_A["url"], "max_age": 3600, "version": version},
        )
        assert response.status_code == 422


class TestServe:
    def test_serve_returns_html(self, client):
        resp = client.post("/cache", json=PAGE_A)
        content_hash = resp.json()["content_hash"]
        response = client.get(f"/cache/serve/{content_hash}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert response.text == PAGE_A["content"]

    def test_serve_etag_header(self, client):
        resp = client.post("/cache", json=PAGE_A)
        content_hash = resp.json()["content_hash"]
        response = client.get(f"/cache/serve/{content_hash}")
        assert response.headers.get("etag") == f'"{content_hash}"'
        assert "immutable" in response.headers.get("cache-control", "")

    def test_serve_304_on_if_none_match(self, client):
        resp = client.post("/cache", json=PAGE_A)
        content_hash = resp.json()["content_hash"]
        response = client.get(
            f"/cache/serve/{content_hash}",
            headers={"if-none-match": f'"{content_hash}"'},
        )
        assert response.status_code == 304

    def test_serve_404_unknown_hash(self, client):
        response = client.get("/cache/serve/" + "c" * 64)
        assert response.status_code == 404


class TestSearch:
    def test_search_returns_matching_entries(self, client):
        client.post("/cache", json=PAGE_A)
        client.post("/cache", json=PAGE_B)
        response = client.get("/cache/search", params={"url_contains": "example.com"})
        assert response.status_code == 200
        urls = [e["url"] for e in response.json()]
        assert PAGE_A["url"] in urls
        assert PAGE_B["url"] in urls

    def test_search_query_param_substring(self, client):
        client.post("/cache", json=PAGE_B)
        response = client.get(
            "/cache/search", params={"url_contains": "example.com/page-b"}
        )
        assert response.status_code == 200
        assert PAGE_B["url"] in [e["url"] for e in response.json()]

    def test_search_no_match_returns_empty_list(self, client):
        response = client.get(
            "/cache/search", params={"url_contains": "this-will-never-match-xyz"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_search_does_not_return_content(self, client):
        client.post("/cache", json=PAGE_A)
        response = client.get("/cache/search", params={"url_contains": "example"})
        for entry in response.json():
            assert "content" not in entry


class TestMeta:
    def test_meta_returns_metadata_no_content(self, client):
        store_resp = client.post("/cache", json=PAGE_A)
        content_hash = store_resp.json()["content_hash"]

        resp = client.get(f"/cache/meta/{content_hash}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_hash"] == content_hash
        assert "content" not in data

    def test_meta_404_unknown_hash(self, client):
        resp = client.get("/cache/meta/" + "a" * 64)
        assert resp.status_code == 404

    def test_meta_respects_bucket(self, client):
        client.post("/cache", json={**PAGE_A, "bucket": "bucket-x"})
        content_hash = _hash(PAGE_A["content"])

        assert client.get(f"/cache/meta/{content_hash}", params={"bucket": "bucket-x"}).status_code == 200
        assert client.get(f"/cache/meta/{content_hash}", params={"bucket": "other-bucket"}).status_code == 404


class TestDelete:
    def test_delete_removes_entry(self, client):
        store_resp = client.post("/cache", json=PAGE_A)
        content_hash = store_resp.json()["content_hash"]

        del_resp = client.delete(f"/cache/{content_hash}")
        assert del_resp.status_code == 204

        get_resp = client.get("/cache", params={"url": PAGE_A["url"]})
        assert get_resp.status_code == 404

    def test_delete_404(self, client):
        response = client.delete("/cache/" + "b" * 64)
        assert response.status_code == 404


class TestHealth:
    def test_health_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestPrefix:
    def test_store_and_retrieve_with_prefix(self, client):
        page = {**PAGE_A, "prefix": "run1/batch2"}
        resp = client.post("/cache", json=page)
        assert resp.status_code == 201
        assert resp.json()["prefix"] == "run1/batch2"

    def test_prefix_stored_in_entry(self, client):
        page = {**PAGE_A, "prefix": "run1"}
        client.post("/cache", json=page)
        resp = client.get("/cache", params={"url": PAGE_A["url"]})
        assert resp.status_code == 200
        assert resp.json()["prefix"] == "run1"
