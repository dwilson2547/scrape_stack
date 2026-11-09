import blake3
import pytest


def test_s3_store_retrieve(s3_client):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 255, 0)).save(buf, format="PNG")
    data = buf.getvalue()

    resp = s3_client.post(
        "/cache",
        data={"url": "http://s3test.com/img.png", "client_name": "s3test",
              "content_hash": blake3.blake3(data).hexdigest()},
        files={"file": ("img.png", data, "image/png")},
    )
    assert resp.status_code == 201
    h = resp.json()["hash"]

    r = s3_client.get(f"/cache/{h}")
    assert r.status_code == 200
    assert r.content == data


def test_s3_dedup(s3_client):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (100, 100, 100)).save(buf, format="PNG")
    data = buf.getvalue()

    r1 = s3_client.post(
        "/cache",
        data={"url": "http://s3test.com/dup.png", "client_name": "s3test",
              "content_hash": blake3.blake3(data).hexdigest()},
        files={"file": ("dup.png", data, "image/png")},
    )
    r2 = s3_client.post(
        "/cache",
        data={"url": "http://s3test.com/dup.png", "client_name": "s3test",
              "content_hash": blake3.blake3(data).hexdigest()},
        files={"file": ("dup.png", data, "image/png")},
    )
    assert r1.status_code == 201
    assert r2.status_code == 200


def test_s3_delete(s3_client):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 200, 200)).save(buf, format="PNG")
    data = buf.getvalue()

    resp = s3_client.post(
        "/cache",
        data={"url": "http://s3test.com/del.png", "client_name": "s3test",
              "content_hash": blake3.blake3(data).hexdigest()},
        files={"file": ("del.png", data, "image/png")},
    )
    h = resp.json()["hash"]
    r = s3_client.delete(f"/cache/{h}")
    assert r.status_code == 204
    r2 = s3_client.get(f"/cache/{h}")
    assert r2.status_code == 404
