"""Tests for custom Prometheus metrics."""


def _page(n: int) -> dict:
    return {
        "url": f"https://example.com/metrics-test/{n}",
        "content": f"<html>unique content {n}</html>",
        "client_name": "metrics_tester",
    }


class TestMetricsEndpoint:
    def test_metrics_endpoint_reachable(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers["content-type"]

    def test_metrics_contains_http_instrumentation(self, client):
        client.get("/health")
        r = client.get("/metrics")
        assert "http_requests_total" in r.text

    def test_store_created_counter_increments(self, client):
        client.post("/cache", json=_page(1))
        r = client.get("/metrics")
        assert 'webcache_store_total{result="created"}' in r.text

    def test_store_duplicate_counter_increments(self, client):
        client.post("/cache", json=_page(2))
        client.post("/cache", json=_page(2))
        r = client.get("/metrics")
        assert 'webcache_store_total{result="duplicate"}' in r.text

    def test_lookup_hit_counter_increments(self, client):
        client.post("/cache", json=_page(3))
        client.get("/cache", params={"url": _page(3)["url"]})
        r = client.get("/metrics")
        assert 'webcache_lookup_total{result="hit"}' in r.text

    def test_lookup_miss_counter_increments(self, client):
        client.get("/cache", params={"url": "https://never-stored.example.com"})
        r = client.get("/metrics")
        assert 'webcache_lookup_total{result="miss"}' in r.text

    def test_compressed_bytes_histogram_present(self, client):
        client.post("/cache", json=_page(4))
        r = client.get("/metrics")
        assert "webcache_compressed_bytes" in r.text

    def test_storage_info_present(self, client):
        r = client.get("/metrics")
        assert "webcache_storage_info" in r.text
        assert 'backend="local"' in r.text
