def test_get_config_returns_defaults(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    # Table is empty in test DB so we get hardcoded defaults from the route
    assert "default_pool_size" in data


def test_update_config(client):
    r = client.patch("/api/config", json={"default_base_delay_ms": 2000, "default_pool_size": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["default_base_delay_ms"] == 2000
    assert data["default_pool_size"] == 3


def test_partial_update_preserves_other_fields(client):
    client.patch("/api/config", json={"default_pool_size": 5})
    r = client.patch("/api/config", json={"default_base_delay_ms": 500})
    assert r.status_code == 200
    data = r.json()
    assert data["default_pool_size"] == 5
    assert data["default_base_delay_ms"] == 500
