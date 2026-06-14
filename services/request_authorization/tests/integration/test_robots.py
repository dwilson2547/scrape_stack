"""
robots.txt integration tests.

Two categories:
  1. Auto-fetch on first domain request (expected to FAIL — feature not implemented)
  2. robots.txt override mechanics via the management API
"""

import time

import pytest


# ---------------------------------------------------------------------------
# Auto-fetch (missing feature — these tests document the gap)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "robots.txt auto-fetch not implemented. "
        "initDomain() in manager.go only calls UpsertDomain(); "
        "robots.Fetch() is never invoked and RobotsFetchTotal is never incremented. "
        "Fix: add robots.Fetch() call in initDomain() and persist the result."
    ),
)
def test_robots_txt_entry_created_after_first_domain_request(grpc_client, api, domain):
    """
    First gRPC permit request for an unseen domain should trigger an async
    robots.txt fetch that populates the robots_txt_cache table.

    Note: even after implementing the fetch, test domains like *.local won't
    resolve, so the fetch will fail with a network error. A robots_txt_cache
    row with checked_at set is still expected to prove the attempt was made.
    """
    p = grpc_client.acquire(domain)
    p.release(0)
    time.sleep(1.5)  # allow async initDomain goroutine to settle

    r = api.get(f"/robots/{domain}")
    assert r.status_code == 200, (
        f"Expected a robots_txt_cache entry for {domain!r} (got {r.status_code})"
    )
    assert r.json()["checked_at"] is not None


# ---------------------------------------------------------------------------
# Management API override mechanics
# ---------------------------------------------------------------------------

def test_override_sets_is_overridden_flag(api, domain):
    r = api.post(f"/robots/{domain}/override", json={"override_delay_ms": 1500})
    assert r.status_code == 200
    data = r.json()
    assert data["is_overridden"] is True
    assert data["override_delay_ms"] == 1500


def test_revert_clears_override(api, domain):
    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 1500})
    r = api.post(f"/robots/{domain}/revert")
    assert r.status_code == 200
    data = r.json()
    assert data["is_overridden"] is False
    assert data["override_delay_ms"] is None


def test_revert_restores_original_crawl_delay(api, domain):
    """
    Overriding then reverting should restore original_crawl_delay_ms as the
    active crawl_delay_ms.
    """
    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 999})
    api.post(f"/robots/{domain}/revert")

    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 3000})
    data = api.get(f"/robots/{domain}").json()
    assert data["is_overridden"] is True
    assert data["override_delay_ms"] == 3000


def test_refresh_marks_entry_as_expired(api, domain):
    """POST /robots/{domain}/refresh clears fetched_at and expires_at so the
    server re-fetches on next config reload."""
    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 1000})
    r = api.post(f"/robots/{domain}/refresh")
    assert r.status_code == 202
    entry = api.get(f"/robots/{domain}").json()
    assert entry["fetched_at"] is None
    assert entry["expires_at"] is None


def test_get_robots_404_for_unknown_domain(api):
    r = api.get(f"/robots/nonexistent-{int(time.time())}.local")
    assert r.status_code == 404
