"""Tests that OTEL metrics are recorded and exposed on GET /metrics."""

from __future__ import annotations

FILE_CONTENT = b"metrics test file content"
FILE_URL = "https://example.com/metrics-test.txt"
FILE_NAME = "metrics-test.txt"
BUCKET = "metrics-bucket"


def _store_file(client):
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    if init["status"] == "cached":
        return init["hash"]
    result = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    return result["hash"]


def test_metrics_endpoint_reachable(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_upload_init_metric_recorded(client):
    client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    })
    metrics_text = client.get("/metrics").text
    assert "filecache_upload_init_total" in metrics_text


def test_ingest_total_metric_recorded(client):
    _store_file(client)
    metrics_text = client.get("/metrics").text
    assert "filecache_ingest_total" in metrics_text


def test_file_bytes_histogram_recorded(client):
    _store_file(client)
    metrics_text = client.get("/metrics").text
    assert "filecache_file_bytes" in metrics_text


def test_lookup_total_metric_recorded(client):
    h = _store_file(client)
    client.get(f"/cache/{h}")
    metrics_text = client.get("/metrics").text
    assert "filecache_lookup_total" in metrics_text


def test_lookup_miss_metric_recorded(client):
    client.get("/cache/nonexistent")
    metrics_text = client.get("/metrics").text
    assert "filecache_lookup_total" in metrics_text
