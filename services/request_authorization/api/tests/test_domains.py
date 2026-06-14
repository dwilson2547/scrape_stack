def test_list_domains_empty(client):
    r = client.get("/api/domains")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_get_domain(client):
    r = client.post("/api/domains", json={"hostname": "rockauto.com", "base_delay_ms": 2000})
    assert r.status_code == 201
    data = r.json()
    assert data["hostname"] == "rockauto.com"
    assert data["base_delay_ms"] == 2000

    r2 = client.get("/api/domains/rockauto.com")
    assert r2.status_code == 200
    assert r2.json()["hostname"] == "rockauto.com"


def test_create_duplicate_domain_returns_400(client):
    client.post("/api/domains", json={"hostname": "rockauto.com"})
    r = client.post("/api/domains", json={"hostname": "rockauto.com"})
    assert r.status_code == 400


def test_update_domain(client):
    client.post("/api/domains", json={"hostname": "autozone.com"})
    r = client.patch("/api/domains/autozone.com", json={"base_delay_ms": 5000})
    assert r.status_code == 200
    assert r.json()["base_delay_ms"] == 5000


def test_delete_domain(client):
    client.post("/api/domains", json={"hostname": "example.com"})
    r = client.delete("/api/domains/example.com")
    assert r.status_code == 204

    r2 = client.get("/api/domains/example.com")
    assert r2.status_code == 404


def test_get_missing_domain_returns_404(client):
    r = client.get("/api/domains/nonexistent.example.com")
    assert r.status_code == 404
