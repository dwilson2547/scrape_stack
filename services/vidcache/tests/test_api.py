"""End-to-end API tests for vidcache."""
from __future__ import annotations

import httpx
import pytest
import respx

VIDEO_CONTENT = b"fake video bytes for testing" * 200
VIDEO_URL = "https://cdn.example.com/clips/sample.mp4"
BUCKET = "test-bucket"
PREFIX = None


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #

def _upload(client, content=VIDEO_CONTENT, url=VIDEO_URL, bucket=BUCKET,
            prefix=PREFIX, filename=None):
    """Full two-phase upload; returns the ingest result dict."""
    body = {"url": url, "bucket": bucket}
    if prefix is not None:
        body["prefix"] = prefix
    if filename is not None:
        body["filename"] = filename
    init = client.post("/upload/init", json=body).json()
    if init["status"] == "cached":
        return init
    return client.post(
        f"/upload/{init['upload_id']}",
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    ).json()


# ---------------------------------------------------------------------- #
# Health                                                                   #
# ---------------------------------------------------------------------- #

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------- #
# POST /upload/init                                                         #
# ---------------------------------------------------------------------- #

def test_upload_init_returns_pending_for_new_url(client):
    resp = client.post("/upload/init", json={"url": VIDEO_URL, "bucket": BUCKET})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "upload_id" in data


def test_upload_init_returns_cached_for_known_url(client):
    _upload(client)
    resp = client.post("/upload/init", json={"url": VIDEO_URL, "bucket": BUCKET})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cached"
    assert "hash" in data
    assert "file_path" in data


# ---------------------------------------------------------------------- #
# POST /upload/{upload_id}                                                  #
# ---------------------------------------------------------------------- #

def test_upload_roundtrip_returns_new(client):
    result = _upload(client)
    assert result["status"] == "new"
    assert len(result["hash"]) == 64
    assert "file_path" in result
    assert result["size_bytes"] == len(VIDEO_CONTENT)


def test_upload_invalid_session_returns_404(client):
    resp = client.post(
        "/upload/deadbeef",
        content=b"data",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 404


def test_upload_session_is_single_use(client):
    init = client.post("/upload/init", json={"url": VIDEO_URL, "bucket": BUCKET}).json()
    uid = init["upload_id"]
    client.post(f"/upload/{uid}", content=VIDEO_CONTENT,
                headers={"Content-Type": "application/octet-stream"})
    resp = client.post(f"/upload/{uid}", content=VIDEO_CONTENT,
                       headers={"Content-Type": "application/octet-stream"})
    assert resp.status_code == 404


def test_upload_duplicate_exact_hash(client):
    r1 = _upload(client, url="https://cdn.example.com/a.mp4")
    r2 = _upload(client, url="https://cdn.example.com/b.mp4")
    assert r2["status"] == "duplicate"
    assert r2["hash"] == r1["hash"]
    assert r2["size_bytes"] == r1["size_bytes"]


def test_upload_different_content_produces_different_hash(client):
    r1 = _upload(client, content=b"alpha" * 100, url="https://example.com/alpha.mp4")
    r2 = _upload(client, content=b"beta" * 100, url="https://example.com/beta.mp4")
    assert r1["hash"] != r2["hash"]
    assert r1["status"] == "new"
    assert r2["status"] == "new"


def test_upload_with_filename_infers_mime(client):
    result = _upload(client, filename="clip.webm")
    video = client.get(f"/cache/meta/{result['hash']}").json()
    assert video["mime_type"] == "video/webm"
    assert video["filename"] == "clip.webm"


# ---------------------------------------------------------------------- #
# GET /cache/{hash}                                                         #
# ---------------------------------------------------------------------- #

def test_get_video_full_content(client):
    result = _upload(client)
    resp = client.get(f"/cache/{result['hash']}")
    assert resp.status_code == 200
    assert resp.content == VIDEO_CONTENT
    assert "Accept-Ranges" in resp.headers


def test_get_video_byte_range(client):
    result = _upload(client)
    resp = client.get(f"/cache/{result['hash']}", headers={"Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert resp.content == VIDEO_CONTENT[:10]
    assert resp.headers["Content-Length"] == "10"
    assert "Content-Range" in resp.headers


def test_get_video_suffix_range(client):
    result = _upload(client)
    resp = client.get(f"/cache/{result['hash']}", headers={"Range": "bytes=-20"})
    assert resp.status_code == 206
    assert resp.content == VIDEO_CONTENT[-20:]


def test_get_video_not_found(client):
    resp = client.get("/cache/" + "a" * 64)
    assert resp.status_code == 404


def test_get_video_content_type(client):
    result = _upload(client, filename="clip.mp4")
    resp = client.get(f"/cache/{result['hash']}")
    assert "video/mp4" in resp.headers["content-type"]


# ---------------------------------------------------------------------- #
# DELETE /cache/{hash}                                                      #
# ---------------------------------------------------------------------- #

def test_delete_video_returns_204(client):
    result = _upload(client)
    h = result["hash"]
    resp = client.delete(f"/cache/{h}")
    assert resp.status_code == 204
    assert client.get(f"/cache/{h}").status_code == 404
    assert client.get(f"/cache/meta/{h}").status_code == 404
    assert client.get(f"/cache/resolve?url={VIDEO_URL}").status_code == 404


def test_delete_not_found(client):
    resp = client.delete("/cache/" + "c" * 64)
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/meta/{hash}                                                    #
# ---------------------------------------------------------------------- #

def test_get_meta(client):
    result = _upload(client)
    resp = client.get(f"/cache/meta/{result['hash']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hash"] == result["hash"]
    assert data["bucket"] == BUCKET
    assert VIDEO_URL in data["aliases"]
    assert "created_at" in data
    assert "retrieved_at" in data


def test_get_meta_multiple_aliases(client):
    r1 = _upload(client, url="https://cdn.example.com/v1.mp4")
    _upload(client, url="https://mirror.example.com/v1.mp4")
    resp = client.get(f"/cache/meta/{r1['hash']}")
    aliases = resp.json()["aliases"]
    assert "https://cdn.example.com/v1.mp4" in aliases
    assert "https://mirror.example.com/v1.mp4" in aliases


def test_get_meta_not_found(client):
    resp = client.get("/cache/meta/" + "b" * 64)
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/resolve                                                        #
# ---------------------------------------------------------------------- #

def test_resolve_known_url(client):
    result = _upload(client)
    resp = client.get(f"/cache/resolve?url={VIDEO_URL}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == result["hash"]


def test_resolve_unknown_url(client):
    resp = client.get("/cache/resolve?url=https://never-seen.example.com/x.mp4")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/lookup                                                         #
# ---------------------------------------------------------------------- #

def test_lookup_no_filter(client):
    result = _upload(client)
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == result["hash"]


def test_lookup_within_max_age(client):
    result = _upload(client)
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}&max_age=3600")
    assert resp.status_code == 200
    assert resp.json()["hash"] == result["hash"]


def test_lookup_exceeded_max_age(client):
    _upload(client)
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}&max_age=0")
    assert resp.status_code == 404


def test_lookup_by_version(client):
    result = _upload(client)
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}&version={result['hash']}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == result["hash"]


def test_lookup_version_not_found(client):
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}&version=" + "d" * 64)
    assert resp.status_code == 404


def test_lookup_max_age_and_version_rejected(client):
    resp = client.get(f"/cache/lookup?url={VIDEO_URL}&max_age=60&version=" + "e" * 64)
    assert resp.status_code == 422


def test_lookup_url_not_found(client):
    resp = client.get("/cache/lookup?url=https://unknown.example.com/x.mp4")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/search                                                         #
# ---------------------------------------------------------------------- #

def test_search_returns_matches(client):
    _upload(client, url="https://cdn.example.com/a.mp4",
            content=b"alpha" * 100, bucket=BUCKET)
    _upload(client, url="https://cdn.example.com/b.mp4",
            content=b"beta" * 100, bucket=BUCKET)
    resp = client.get(f"/cache/search?url_contains=cdn.example.com&bucket={BUCKET}")
    assert resp.status_code == 200
    urls = [r["url"] for r in resp.json()]
    assert "https://cdn.example.com/a.mp4" in urls
    assert "https://cdn.example.com/b.mp4" in urls


def test_search_no_matches(client):
    resp = client.get("/cache/search?url_contains=zzznomatch&bucket=test-bucket")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------- #
# Perceptual hash dedup                                                     #
# ---------------------------------------------------------------------- #

def test_upload_dedup_via_phash(client, monkeypatch):
    import app.dedup as dedup_module
    monkeypatch.setattr(dedup_module, "_compute_phash", lambda path: "abcd1234")

    r1 = _upload(client, content=b"video-alpha" * 500, url="https://example.com/va.mp4")
    assert r1["status"] == "new"

    r2 = _upload(client, content=b"video-beta" * 500, url="https://example.com/vb.mp4")
    assert r2["status"] == "duplicate"
    assert r2["hash"] == r1["hash"]
    assert r2.get("phash_distance") == 0


def test_phash_dedup_respects_threshold(client, monkeypatch):
    import app.dedup as dedup_module
    call_count = 0

    def _mock_phash(path):
        nonlocal call_count
        call_count += 1
        return "0000ffff" if call_count == 1 else "ffff0000"

    monkeypatch.setattr(dedup_module, "_compute_phash", _mock_phash)

    r1 = _upload(client, content=b"alpha" * 500, url="https://example.com/pa.mp4")
    r2 = _upload(client, content=b"beta" * 500, url="https://example.com/pb.mp4")
    assert r1["status"] == "new"
    assert r2["status"] == "new"


# ---------------------------------------------------------------------- #
# POST /download  (server-side download via request_auth)                  #
# ---------------------------------------------------------------------- #

def test_download_returns_cached_for_known_url(client):
    r = _upload(client)
    resp = client.post("/download", json={"url": VIDEO_URL, "bucket": BUCKET})
    assert resp.status_code == 200
    data = resp.json()
    assert data["hash"] == r["hash"]


@respx.mock
def test_download_fetches_and_stores_new_url(client):
    url = "https://cdn.example.com/server-dl.mp4"
    content = b"server fetched video" * 100
    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    resp = client.post("/download", json={"url": url, "bucket": BUCKET, "filename": "server-dl.mp4"})
    assert resp.status_code == 200
    data = resp.json()
    assert "hash" in data
    assert len(data["hash"]) == 64

    stream = client.get(f"/cache/{data['hash']}")
    assert stream.status_code == 200
    assert stream.content == content


@respx.mock
def test_download_502_on_upstream_error(client):
    url = "https://cdn.example.com/broken.mp4"
    respx.get(url).mock(return_value=httpx.Response(404))

    resp = client.post("/download", json={"url": url, "bucket": BUCKET})
    assert resp.status_code == 502


def test_download_503_without_request_auth(client):
    import app.request_auth as ra_module
    ra_module.reset_client()
    resp = client.post("/download", json={"url": VIDEO_URL, "bucket": BUCKET})
    assert resp.status_code == 503


# ---------------------------------------------------------------------- #
# Prefix routing                                                            #
# ---------------------------------------------------------------------- #

def test_upload_with_prefix(client):
    result = _upload(client, prefix="run1/batch2")
    assert result["status"] == "new"
    stream = client.get(f"/cache/{result['hash']}")
    assert stream.status_code == 200
    assert stream.content == VIDEO_CONTENT


def test_same_content_different_prefix_is_duplicate(client):
    r1 = _upload(client, url="https://example.com/p1.mp4", prefix="run1")
    r2 = _upload(client, url="https://example.com/p2.mp4", prefix="run2")
    assert r1["hash"] == r2["hash"]
    assert r2["status"] == "duplicate"
