"""
Bucket retention tests: max_entries / max_total_bytes configs, automatic
eviction on store, manual enforce, and storage-file sharing safety.
"""

import blake3


def _hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


def _page(url: str, content: str, bucket: str = "default") -> dict:
    return {
        "url": url,
        "content": content,
        "content_hash": _hash(content),
        "client_name": "test_scraper",
        "bucket": bucket,
    }


class TestBucketConfigs:
    def test_put_and_list(self, client):
        resp = client.put("/buckets/latest_thousand", json={"max_entries": 1000})
        assert resp.status_code == 200
        body = resp.json()
        assert body["bucket"] == "latest_thousand"
        assert body["max_entries"] == 1000
        assert body["max_total_bytes"] is None
        assert body["stats"]["entries"] == 0

        listed = client.get("/buckets").json()
        assert any(b["bucket"] == "latest_thousand" for b in listed)

    def test_put_validates(self, client):
        assert client.put("/buckets/x", json={"max_entries": 0}).status_code == 422
        assert client.put("/buckets/x", json={"max_total_bytes": -5}).status_code == 422

    def test_update_config(self, client):
        client.put("/buckets/b1", json={"max_entries": 10})
        resp = client.put("/buckets/b1", json={"max_entries": 5, "max_total_bytes": 1024})
        assert resp.json()["max_entries"] == 5
        assert resp.json()["max_total_bytes"] == 1024

    def test_delete_config_keeps_entries(self, client):
        client.post("/cache", json=_page("https://example.com/a", "A", bucket="b1"))
        client.put("/buckets/b1", json={"max_entries": 1})
        assert client.delete("/buckets/b1").status_code == 204
        assert client.get("/cache", params={"url": "https://example.com/a", "bucket": "b1"}).status_code == 200

    def test_enforce_404_without_config(self, client):
        assert client.post("/buckets/none/enforce").status_code == 404


class TestAutoEviction:
    def test_max_entries_keeps_newest(self, client):
        client.put("/buckets/latest_two", json={"max_entries": 2})
        for i in range(4):
            client.post("/cache", json=_page(f"https://example.com/p{i}", f"page {i}", bucket="latest_two"))

        stats = client.get("/buckets").json()
        b = next(x for x in stats if x["bucket"] == "latest_two")
        assert b["stats"]["entries"] == 2

        # newest survive, oldest evicted
        assert client.get("/cache", params={"url": "https://example.com/p2", "bucket": "latest_two"}).status_code == 200
        assert client.get("/cache", params={"url": "https://example.com/p3", "bucket": "latest_two"}).status_code == 200
        assert client.get("/cache", params={"url": "https://example.com/p0", "bucket": "latest_two"}).status_code == 404
        assert client.get("/cache", params={"url": "https://example.com/p1", "bucket": "latest_two"}).status_code == 404

    def test_no_config_no_eviction(self, client):
        for i in range(5):
            client.post("/cache", json=_page(f"https://example.com/q{i}", f"q {i}", bucket="unbounded"))
        assert client.get("/cache", params={"url": "https://example.com/q0", "bucket": "unbounded"}).status_code == 200

    def test_manual_enforce_retrofits(self, client):
        for i in range(6):
            client.post("/cache", json=_page(f"https://example.com/r{i}", f"r {i}", bucket="backlog"))
        client.put("/buckets/backlog", json={"max_entries": 6})  # at limit, nothing evicted
        resp = client.put("/buckets/backlog", json={"max_entries": 2})
        assert resp.json()["stats"]["entries"] == 2
        evicted = client.post("/buckets/backlog/enforce").json()
        assert evicted == {"bucket": "backlog", "evicted": 0}


class TestStorageSafety:
    def test_shared_file_survives_partial_eviction(self, client):
        """Two URLs with identical content share one storage file (keyed by
        content hash); evicting one entry must not delete the shared file
        while the other entry still references it."""
        content = "<html>identical</html>"
        client.put("/buckets/share", json={"max_entries": 2})
        client.post("/cache", json=_page("https://example.com/one", content, bucket="share"))
        client.post("/cache", json=_page("https://example.com/two", content, bucket="share"))

        # third store evicts the OLDEST entry ("one"); "two" still needs the
        # shared content file — it must remain readable
        client.post("/cache", json=_page("https://example.com/three", "different", bucket="share"))

        stats = client.get("/buckets").json()
        b = next(x for x in stats if x["bucket"] == "share")
        assert b["stats"]["entries"] == 2
        survivor = client.get("/cache", params={"url": "https://example.com/two", "bucket": "share"})
        assert survivor.status_code == 200
        assert survivor.json()["content"] == content
