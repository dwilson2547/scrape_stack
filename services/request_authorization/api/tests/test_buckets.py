def test_create_and_list_buckets(client):
    r = client.post("/api/buckets", json={"name": "cdn-bucket", "pool_size": 10, "base_delay_ms": 0})
    assert r.status_code == 201
    assert r.json()["name"] == "cdn-bucket"

    r2 = client.get("/api/buckets")
    assert len(r2.json()) == 1


def test_bucket_detail_includes_domains(client):
    rb = client.post("/api/buckets", json={"name": "test-bucket"})
    bucket_id = rb.json()["id"]

    rd = client.post("/api/domains", json={"hostname": "example.com"})
    domain_id = rd.json()["id"]

    r = client.post(f"/api/buckets/{bucket_id}/domains", json={"domain_id": domain_id})
    assert r.status_code == 204

    detail = client.get(f"/api/buckets/{bucket_id}").json()
    assert len(detail["domains"]) == 1
    assert detail["domains"][0]["hostname"] == "example.com"


def test_remove_domain_from_bucket(client):
    rb = client.post("/api/buckets", json={"name": "b"})
    bucket_id = rb.json()["id"]
    rd = client.post("/api/domains", json={"hostname": "x.com"})
    domain_id = rd.json()["id"]
    client.post(f"/api/buckets/{bucket_id}/domains", json={"domain_id": domain_id})

    r = client.delete(f"/api/buckets/{bucket_id}/domains/{domain_id}")
    assert r.status_code == 204

    detail = client.get(f"/api/buckets/{bucket_id}").json()
    assert len(detail["domains"]) == 0


def test_delete_bucket(client):
    r = client.post("/api/buckets", json={"name": "to-delete"})
    bid = r.json()["id"]
    r2 = client.delete(f"/api/buckets/{bid}")
    assert r2.status_code == 204


def test_duplicate_bucket_returns_400(client):
    client.post("/api/buckets", json={"name": "dup"})
    r = client.post("/api/buckets", json={"name": "dup"})
    assert r.status_code == 400
