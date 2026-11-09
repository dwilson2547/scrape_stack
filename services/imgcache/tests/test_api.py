import blake3
import io
import pytest
from PIL import Image


def make_png_bytes(size=(100, 100), color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _hash(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def store_image(client, url="http://example.com/test.png", client_name="test",
                bucket="", prefix="", data=None):
    if data is None:
        data = make_png_bytes()
    return client.post(
        "/cache",
        data={
            "url": url,
            "client_name": client_name,
            "content_hash": _hash(data),
            "bucket": bucket,
            "prefix": prefix,
        },
        files={"file": ("test.png", data, "image/png")},
    )


# ---------------------------------------------------------------------- #
# Health                                                                   #
# ---------------------------------------------------------------------- #

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------- #
# POST /cache                                                               #
# ---------------------------------------------------------------------- #

def test_store_new(client):
    resp = store_image(client)
    assert resp.status_code == 201
    body = resp.json()
    assert "hash" in body
    assert body["url"] == "http://example.com/test.png"
    assert "mime_type" in body
    assert "size_bytes" in body
    assert "retrieved_at" in body


def test_store_duplicate_returns_200(client):
    r1 = store_image(client)
    r2 = store_image(client)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["hash"] == r2.json()["hash"]


def test_store_wrong_hash_rejected(client):
    data = make_png_bytes()
    resp = client.post(
        "/cache",
        data={"url": "http://example.com/x.png", "client_name": "test",
              "content_hash": "a" * 64},
        files={"file": ("x.png", data, "image/png")},
    )
    assert resp.status_code == 422


def test_store_with_prefix(client):
    resp = store_image(client, prefix="run1/batch2")
    assert resp.status_code == 201
    assert resp.json()["prefix"] == "run1/batch2"


def test_store_non_image_rejected(client):
    data = b"this is not an image"
    resp = client.post(
        "/cache",
        data={"url": "http://example.com/x.bin", "client_name": "test",
              "content_hash": _hash(data)},
        files={"file": ("x.bin", data, "application/octet-stream")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------- #
# GET /cache/{hash}                                                         #
# ---------------------------------------------------------------------- #

def test_get_image_bytes(client):
    resp = store_image(client)
    h = resp.json()["hash"]
    r = client.get(f"/cache/{h}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert len(r.content) > 0


def test_get_image_not_found(client):
    assert client.get("/cache/" + "a" * 64).status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/meta/{hash}                                                    #
# ---------------------------------------------------------------------- #

def test_get_meta(client):
    resp = store_image(client)
    h = resp.json()["hash"]
    r = client.get(f"/cache/meta/{h}")
    assert r.status_code == 200
    body = r.json()
    assert body["hash"] == h
    assert "id" not in body
    assert "retrieved_at" in body


def test_get_meta_not_found(client):
    assert client.get("/cache/meta/" + "b" * 64).status_code == 404


# ---------------------------------------------------------------------- #
# DELETE /cache/{hash}                                                      #
# ---------------------------------------------------------------------- #

def test_delete(client):
    resp = store_image(client)
    h = resp.json()["hash"]
    assert client.delete(f"/cache/{h}").status_code == 204
    assert client.get(f"/cache/{h}").status_code == 404


def test_delete_not_found(client):
    assert client.delete("/cache/" + "c" * 64).status_code == 404


# ---------------------------------------------------------------------- #
# GET /cache/lookup                                                         #
# ---------------------------------------------------------------------- #

def test_lookup_hit(client):
    url = "http://example.com/unique.png"
    store_image(client, url=url)
    r = client.get(f"/cache/lookup?url={url}")
    assert r.status_code == 200
    assert r.json()["url"] == url


def test_lookup_miss(client):
    assert client.get("/cache/lookup?url=http://example.com/nothere.png").status_code == 404


def test_lookup_within_max_age(client):
    url = "http://example.com/fresh.png"
    store_image(client, url=url)
    r = client.get(f"/cache/lookup?url={url}&max_age=3600")
    assert r.status_code == 200


def test_lookup_exceeded_max_age(client):
    url = "http://example.com/stale.png"
    store_image(client, url=url)
    r = client.get(f"/cache/lookup?url={url}&max_age=0")
    assert r.status_code == 404


def test_lookup_by_version(client):
    resp = store_image(client, url="http://example.com/v.png")
    h = resp.json()["hash"]
    r = client.get(f"/cache/lookup?url=http://example.com/v.png&version={h}")
    assert r.status_code == 200
    assert r.json()["hash"] == h


def test_lookup_max_age_and_version_rejected(client):
    r = client.get("/cache/lookup?url=http://example.com/x.png&max_age=60&version=" + "d" * 64)
    assert r.status_code == 422


# ---------------------------------------------------------------------- #
# GET /cache/search                                                         #
# ---------------------------------------------------------------------- #

def test_search_match(client):
    store_image(client, url="http://example.com/images/cat.png")
    store_image(client, url="http://other.com/dog.png", client_name="other",
                data=make_png_bytes(color=(0, 255, 0)))
    r = client.get("/cache/search?url_contains=example.com")
    assert r.status_code == 200
    results = r.json()
    assert len(results) >= 1
    assert all("example.com" in x["url"] for x in results)


def test_search_empty(client):
    r = client.get("/cache/search?url_contains=zzznomatch")
    assert r.status_code == 200
    assert r.json() == []


def test_search_response_has_no_binary(client):
    store_image(client)
    r = client.get("/cache/search?url_contains=example.com")
    assert r.status_code == 200
    for item in r.json():
        assert "file" not in item
        assert "data" not in item


# ---------------------------------------------------------------------- #
# GET /cache/serve/{hash}                                                   #
# ---------------------------------------------------------------------- #

def test_serve_image(client):
    resp = store_image(client)
    h = resp.json()["hash"]
    r = client.get(f"/cache/serve/{h}")
    assert r.status_code == 200
    assert "ETag" in r.headers
    assert r.headers.get("Cache-Control", "") == "public, max-age=31536000, immutable"


def test_serve_etag_304(client):
    resp = store_image(client)
    h = resp.json()["hash"]
    r = client.get(f"/cache/serve/{h}", headers={"if-none-match": f'"{h}"'})
    assert r.status_code == 304


# ---------------------------------------------------------------------- #
# GET /cache/resolve                                                        #
# ---------------------------------------------------------------------- #

def test_resolve_known_url(client):
    r = store_image(client, url="http://example.com/pic.png")
    expected_hash = r.json()["hash"]
    resp = client.get("/cache/resolve", params={"url": "http://example.com/pic.png"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["hash"] == expected_hash
    assert body["url"] == "http://example.com/pic.png"


def test_resolve_unknown_url(client):
    resp = client.get("/cache/resolve", params={"url": "http://nobody.com/nope.png"})
    assert resp.status_code == 404


def test_resolve_bucket_isolation(client):
    data = make_png_bytes()
    store_image(client, url="http://example.com/img.png", bucket="a", data=data)
    # query wrong bucket — should 404
    resp = client.get("/cache/resolve", params={"url": "http://example.com/img.png", "bucket": "b"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------- #
# aliases field in responses                                                #
# ---------------------------------------------------------------------- #

def test_aliases_in_store_response(client):
    resp = store_image(client, url="http://example.com/a.png")
    body = resp.json()
    assert "aliases" in body
    assert body["url"] in body["aliases"]


def test_aliases_in_meta_response(client):
    resp = store_image(client, url="http://example.com/b.png")
    h = resp.json()["hash"]
    r = client.get(f"/cache/meta/{h}")
    assert r.status_code == 200
    body = r.json()
    assert "aliases" in body
    assert body["url"] in body["aliases"]
