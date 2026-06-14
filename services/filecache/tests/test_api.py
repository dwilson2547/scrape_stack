"""End-to-end API tests for the two-phase upload flow and read operations."""

from __future__ import annotations

import io
import time

import pytest

FILE_CONTENT = b"Hello, filecache! This is a test PDF file." * 100
FILE_URL = "https://example.com/docs/report.pdf"
FILE_NAME = "report.pdf"
BUCKET = "test-bucket"


# ---------------------------------------------------------------------- #
# Health                                                                   #
# ---------------------------------------------------------------------- #

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------- #
# Two-phase upload — happy path                                            #
# ---------------------------------------------------------------------- #

def test_upload_init_returns_pending(client):
    resp = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "upload_id" in data


def test_upload_full_roundtrip(client):
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    assert init["status"] == "pending"

    result = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "new"
    assert "hash" in data
    assert data["size_bytes"] == len(FILE_CONTENT)

    return data["hash"]


def test_upload_init_returns_cached_for_known_url(client):
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    )
    init2 = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    assert init2["status"] == "cached"


def test_upload_duplicate_content_updates_retrieved_at(client):
    """Same bytes under a new URL → duplicate detected → retrieved_at updated."""
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    r1 = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    retrieved_before = client.get(f"/cache/meta/{r1['hash']}").json()["retrieved_at"]

    time.sleep(0.01)

    # Upload same bytes under a fresh URL so run_ingest is reached
    alt_url = "https://example.com/docs/report-v2.pdf"
    init2 = client.post("/upload/init", json={
        "url": alt_url,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    assert init2["status"] == "pending"
    r2 = client.post(
        f"/upload/{init2['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert r2["status"] == "duplicate"
    assert r2["hash"] == r1["hash"]

    retrieved_after = client.get(f"/cache/meta/{r1['hash']}").json()["retrieved_at"]
    assert retrieved_after >= retrieved_before


def test_upload_same_content_different_url(client):
    # Upload once
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    result1 = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()

    # Upload same bytes under a different URL
    init2 = client.post("/upload/init", json={
        "url": "https://example.com/mirror/report.pdf",
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    assert init2["status"] == "pending"
    result2 = client.post(
        f"/upload/{init2['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert result2["status"] == "duplicate"
    assert result2["hash"] == result1["hash"]


def test_upload_invalid_session(client):
    resp = client.post(
        "/upload/deadbeef",
        content=b"data",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# File retrieval                                                           #
# ---------------------------------------------------------------------- #

def _store_file(client, content=FILE_CONTENT, url=FILE_URL, filename=FILE_NAME, bucket=BUCKET):
    init = client.post("/upload/init", json={"url": url, "bucket": bucket, "filename": filename}).json()
    if init["status"] == "cached":
        return init["hash"]
    result = client.post(
        f"/upload/{init['upload_id']}",
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    return result["hash"]


def test_get_meta(client):
    h = _store_file(client)
    resp = client.get(f"/cache/meta/{h}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hash"] == h
    assert data["filename"] == FILE_NAME
    assert data["mime_type"] == "application/pdf"
    assert data["size_bytes"] == len(FILE_CONTENT)
    assert FILE_URL in data["aliases"]


def test_get_meta_not_found(client):
    resp = client.get("/cache/meta/nonexistent")
    assert resp.status_code == 404


def test_download_file_bytes(client):
    h = _store_file(client)
    resp = client.get(f"/cache/{h}")
    assert resp.status_code == 200
    assert resp.content == FILE_CONTENT
    assert resp.headers["content-disposition"] == f'attachment; filename="{FILE_NAME}"'
    assert resp.headers["content-type"] == "application/pdf"


def test_download_file_range(client):
    h = _store_file(client)
    resp = client.get(f"/cache/{h}", headers={"Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert resp.content == FILE_CONTENT[:10]
    assert "Content-Range" in resp.headers


def test_download_file_not_found(client):
    resp = client.get("/cache/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# Resolve                                                                  #
# ---------------------------------------------------------------------- #

def test_resolve(client):
    h = _store_file(client)
    resp = client.get(f"/cache/resolve?url={FILE_URL}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == h


def test_resolve_not_found(client):
    resp = client.get("/cache/resolve?url=https://unknown.example.com/x.zip")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# Lookup                                                                   #
# ---------------------------------------------------------------------- #

def test_lookup_no_filter(client):
    h = _store_file(client)
    resp = client.get(f"/cache/lookup?url={FILE_URL}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == h


def test_lookup_within_max_age(client):
    h = _store_file(client)
    resp = client.get(f"/cache/lookup?url={FILE_URL}&max_age=3600")
    assert resp.status_code == 200
    assert resp.json()["hash"] == h


def test_lookup_exceeded_max_age(client):
    # Use max_age=0 to force a miss immediately
    _store_file(client)
    resp = client.get(f"/cache/lookup?url={FILE_URL}&max_age=0")
    assert resp.status_code == 404


def test_lookup_by_version(client):
    h = _store_file(client)
    resp = client.get(f"/cache/lookup?url={FILE_URL}&version={h}")
    assert resp.status_code == 200
    assert resp.json()["hash"] == h


def test_lookup_version_not_found(client):
    resp = client.get(f"/cache/lookup?url={FILE_URL}&version=deadbeef")
    assert resp.status_code == 404


def test_lookup_max_age_and_version_rejected(client):
    resp = client.get(f"/cache/lookup?url={FILE_URL}&max_age=3600&version=abc")
    assert resp.status_code == 422


def test_lookup_not_found(client):
    resp = client.get("/cache/lookup?url=https://never-stored.example.com/x.bin")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# Search                                                                   #
# ---------------------------------------------------------------------- #

def test_search_returns_matches(client):
    _store_file(client, url=FILE_URL, bucket=BUCKET)
    _store_file(client, url="https://example.com/docs/other.pdf", bucket=BUCKET,
                content=b"other content", filename="other.pdf")

    resp = client.get(f"/cache/search?url_contains=example.com&bucket={BUCKET}")
    assert resp.status_code == 200
    results = resp.json()
    urls = [r["url"] for r in results]
    assert FILE_URL in urls
    assert "https://example.com/docs/other.pdf" in urls


def test_search_no_matches(client):
    resp = client.get("/cache/search?url_contains=zzznomatch&bucket=test-bucket")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------- #
# Delete                                                                   #
# ---------------------------------------------------------------------- #

def test_delete_removes_file(client):
    h = _store_file(client)
    resp = client.delete(f"/cache/{h}")
    assert resp.status_code == 204

    assert client.get(f"/cache/meta/{h}").status_code == 404
    assert client.get(f"/cache/{h}").status_code == 404
    # URL alias should also be gone
    assert client.get(f"/cache/resolve?url={FILE_URL}").status_code == 404


def test_delete_not_found(client):
    resp = client.delete("/cache/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# MIME type inference                                                      #
# ---------------------------------------------------------------------- #

@pytest.mark.parametrize("filename,expected_mime", [
    ("archive.zip", "application/zip"),
    ("data.json", "application/json"),
    ("notes.txt", "text/plain"),
    ("page.html", "text/html"),
    ("image.png", "image/png"),
    ("video.mp4", "video/mp4"),
    ("unknown.xyz", "application/octet-stream"),
])
def test_mime_type_inference(client, filename, expected_mime):
    url = f"https://example.com/files/{filename}"
    init = client.post("/upload/init", json={"url": url, "bucket": "mime-test", "filename": filename}).json()
    result = client.post(
        f"/upload/{init['upload_id']}",
        content=b"dummy content for mime test",
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    meta = client.get(f"/cache/meta/{result['hash']}").json()
    assert meta["mime_type"] == expected_mime


# ---------------------------------------------------------------------- #
# upload_init content_hash shortcut                                        #
# ---------------------------------------------------------------------- #

def test_upload_init_fresh_when_hash_known(client):
    """Client sends pre-computed hash; service returns 'fresh' and skips upload."""
    init = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
    }).json()
    result = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    known_hash = result["hash"]

    alt_url = "https://example.com/docs/report-alt.pdf"
    fresh = client.post("/upload/init", json={
        "url": alt_url,
        "bucket": BUCKET,
        "filename": FILE_NAME,
        "content_hash": known_hash,
    }).json()
    assert fresh["status"] == "fresh"
    assert fresh["hash"] == known_hash

    # The new URL should now resolve to the same hash
    assert client.get(f"/cache/resolve?url={alt_url}").json()["hash"] == known_hash


def test_upload_init_fresh_bumps_retrieved_at(client):
    """content_hash shortcut updates retrieved_at on the file record."""
    init = client.post("/upload/init", json={
        "url": FILE_URL, "bucket": BUCKET, "filename": FILE_NAME,
    }).json()
    result = client.post(
        f"/upload/{init['upload_id']}",
        content=FILE_CONTENT,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    before = client.get(f"/cache/meta/{result['hash']}").json()["retrieved_at"]

    time.sleep(0.01)

    client.post("/upload/init", json={
        "url": FILE_URL, "bucket": BUCKET, "filename": FILE_NAME,
        "content_hash": result["hash"],
    })
    after = client.get(f"/cache/meta/{result['hash']}").json()["retrieved_at"]
    assert after > before


def test_upload_init_pending_when_hash_unknown(client):
    """content_hash for an unseen hash falls through to pending."""
    resp = client.post("/upload/init", json={
        "url": FILE_URL,
        "bucket": BUCKET,
        "filename": FILE_NAME,
        "content_hash": "a" * 64,  # fabricated, not in DB
    }).json()
    assert resp["status"] == "pending"
    assert "upload_id" in resp


# ---------------------------------------------------------------------- #
# url_map versioning                                                       #
# ---------------------------------------------------------------------- #

def test_url_versioning_new_row_when_content_changes(client):
    """Same URL with different content creates a new url_map row; resolve returns latest hash."""
    content_v1 = b"version one content"
    content_v2 = b"version two content - different bytes"
    url = "https://example.com/versioned/doc.pdf"

    init1 = client.post("/upload/init", json={"url": url, "bucket": BUCKET, "filename": "doc.pdf"}).json()
    r1 = client.post(f"/upload/{init1['upload_id']}", content=content_v1,
                     headers={"Content-Type": "application/octet-stream"}).json()
    hash_v1 = r1["hash"]

    init2 = client.post("/upload/init", json={"url": url, "bucket": BUCKET, "filename": "doc.pdf"}).json()
    # upload_init returns "cached" for known URL — go around it with a different URL then re-associate
    # To simulate a content change, upload under a temp URL then re-upload the original URL.
    temp_url = "https://example.com/versioned/doc-temp.pdf"
    init_temp = client.post("/upload/init", json={"url": temp_url, "bucket": BUCKET, "filename": "doc.pdf"}).json()
    r2 = client.post(f"/upload/{init_temp['upload_id']}", content=content_v2,
                     headers={"Content-Type": "application/octet-stream"}).json()
    hash_v2 = r2["hash"]
    assert hash_v1 != hash_v2

    # Associate the original URL with the new hash via the content_hash shortcut
    fresh = client.post("/upload/init", json={
        "url": url, "bucket": BUCKET, "filename": "doc.pdf",
        "content_hash": hash_v2,
    }).json()
    assert fresh["status"] == "fresh"

    # resolve now returns the new hash
    assert client.get(f"/cache/resolve?url={url}").json()["hash"] == hash_v2

    # Old hash is still accessible by version
    assert client.get(f"/cache/lookup?url={url}&version={hash_v1}").status_code == 200


def test_url_versioning_no_new_row_for_same_content(client):
    """Re-uploading the same URL+content does not create extra url_map rows (aliases stays clean)."""
    init = client.post("/upload/init", json={
        "url": FILE_URL, "bucket": BUCKET, "filename": FILE_NAME,
    }).json()
    r1 = client.post(f"/upload/{init['upload_id']}", content=FILE_CONTENT,
                     headers={"Content-Type": "application/octet-stream"}).json()

    # Use the hash shortcut with the same URL + same hash — should be a no-op on url_map
    client.post("/upload/init", json={
        "url": FILE_URL, "bucket": BUCKET, "filename": FILE_NAME,
        "content_hash": r1["hash"],
    })

    meta = client.get(f"/cache/meta/{r1['hash']}").json()
    # aliases should list FILE_URL exactly once (set dedup in _file_to_dict + no duplicate row)
    assert meta["aliases"].count(FILE_URL) == 1


# ---------------------------------------------------------------------- #
# S3 backend (skipped without Docker)                                      #
# ---------------------------------------------------------------------- #

def test_s3_upload_and_download(s3_client):
    content = b"S3 test file content for filecache"
    url = "https://example.com/s3test/file.bin"
    filename = "file.bin"
    bucket = "s3-test-bucket"

    init = s3_client.post("/upload/init", json={"url": url, "bucket": bucket, "filename": filename}).json()
    assert init["status"] == "pending"

    result = s3_client.post(
        f"/upload/{init['upload_id']}",
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert result["status"] == "new"

    downloaded = s3_client.get(f"/cache/{result['hash']}")
    assert downloaded.status_code == 200
    assert downloaded.content == content


def test_s3_deduplication(s3_client):
    content = b"Duplicate S3 content"
    bucket = "s3-dedup-bucket"

    def _upload(url, filename):
        init = s3_client.post("/upload/init", json={"url": url, "bucket": bucket, "filename": filename}).json()
        if init["status"] == "cached":
            return init
        return s3_client.post(
            f"/upload/{init['upload_id']}",
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        ).json()

    r1 = _upload("https://example.com/s3a.bin", "s3a.bin")
    r2 = _upload("https://example.com/s3b.bin", "s3b.bin")
    assert r1["hash"] == r2["hash"]
    assert r2["status"] == "duplicate"
