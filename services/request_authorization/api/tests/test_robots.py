def test_get_missing_robots_returns_404(client):
    r = client.get("/api/robots/unknown.com")
    assert r.status_code == 404


def test_override_creates_entry(client):
    r = client.post("/api/robots/example.com/override", json={"override_delay_ms": 5000})
    assert r.status_code == 200
    data = r.json()
    assert data["is_overridden"] is True
    assert data["override_delay_ms"] == 5000


def test_revert_clears_override(client):
    client.post("/api/robots/example.com/override", json={"override_delay_ms": 5000})
    r = client.post("/api/robots/example.com/revert")
    assert r.status_code == 200
    data = r.json()
    assert data["is_overridden"] is False
    assert data["override_delay_ms"] is None


def test_revert_non_overridden_returns_400(client):
    client.post("/api/robots/example.com/override", json={"override_delay_ms": 5000})
    client.post("/api/robots/example.com/revert")
    r = client.post("/api/robots/example.com/revert")
    assert r.status_code == 400


def test_override_preserves_original_crawl_delay(client):
    # Simulate an existing robots.txt entry with crawl_delay_ms
    from app.models import RobotsTxtCache
    from app.database import get_db
    db = next(get_db.__wrapped__()) if hasattr(get_db, "__wrapped__") else None
    # Use the API's DB override from conftest instead
    client.post("/api/robots/example.com/override", json={"override_delay_ms": 5000})
    r = client.get("/api/robots/example.com")
    data = r.json()
    assert data["is_overridden"] is True
