"""
Config priority chain tests.

The Go server resolves config in this order (highest wins):
  domain-level explicit settings
    → bucket settings
      → robots.txt crawl-delay (only when domain has no explicit base_delay and no bucket)
        → global defaults

Each test uses a fresh domain (function-scoped fixture) so pool config is
read from the DB at pool-creation time, not from a cached/reloaded pool.

We read current_delay_ms from the /status endpoint while holding a permit
rather than measuring wall-clock time, so these tests are fast and precise.
"""

import uuid

import pytest

from conftest import get_pool_status

GLOBAL_DEFAULT_BASE_DELAY_MS = 1000  # schema default from schema.sql


def _read_delay(grpc_client, status_client, domain) -> int:
    """Acquire a permit (creates pool on first call), read delay, release."""
    p = grpc_client.acquire(domain)
    st = get_pool_status(status_client, domain)
    assert st is not None, f"no pool status for {domain!r}"
    p.release(200)
    return st["current_delay_ms"]


# ---------------------------------------------------------------------------
# Global defaults
# ---------------------------------------------------------------------------

def test_unknown_domain_uses_global_default(grpc_client, status_client, domain):
    """
    A domain with no DB entry and no bucket falls back to global
    default_base_delay_ms (1000ms as seeded by schema.sql).
    """
    delay = _read_delay(grpc_client, status_client, domain)
    assert delay == GLOBAL_DEFAULT_BASE_DELAY_MS, (
        f"expected global default {GLOBAL_DEFAULT_BASE_DELAY_MS}ms, got {delay}ms"
    )


# ---------------------------------------------------------------------------
# Bucket settings
# ---------------------------------------------------------------------------

def test_bucket_base_delay_overrides_global(grpc_client, api, status_client, domain):
    """A bucket with base_delay_ms=300 overrides the global 1000ms default."""
    bucket_name = f"bkt-{uuid.uuid4().hex[:6]}"
    r = api.post("/buckets", json={"name": bucket_name, "base_delay_ms": 300})
    assert r.status_code == 201, r.text
    bucket_id = r.json()["id"]

    api.post("/domains", json={"name": domain, "bucket_id": bucket_id})

    delay = _read_delay(grpc_client, status_client, domain)
    assert delay == 300, f"expected bucket delay 300ms, got {delay}ms"


def test_bucket_pool_size_overrides_global(grpc_client, api, status_client, domain):
    """A bucket with pool_size=5 is honoured by the permit server."""
    bucket_name = f"bkt-{uuid.uuid4().hex[:6]}"
    r = api.post("/buckets", json={"name": bucket_name, "pool_size": 5})
    assert r.status_code == 201
    bucket_id = r.json()["id"]

    api.post("/domains", json={"name": domain, "bucket_id": bucket_id})
    p = grpc_client.acquire(domain)
    st = get_pool_status(status_client, domain)
    p.release(200)
    assert st["active"] + st["queued"] + (1 if st["active"] == 0 else 0) <= 5


# ---------------------------------------------------------------------------
# Domain-level settings beat bucket
# ---------------------------------------------------------------------------

def test_domain_base_delay_overrides_bucket(grpc_client, api, status_client, domain):
    """Explicit domain base_delay_ms wins over the bucket's base_delay_ms."""
    bucket_name = f"bkt-{uuid.uuid4().hex[:6]}"
    r = api.post("/buckets", json={"name": bucket_name, "base_delay_ms": 800})
    bucket_id = r.json()["id"]

    api.post("/domains", json={"name": domain, "bucket_id": bucket_id, "base_delay_ms": 120})

    delay = _read_delay(grpc_client, status_client, domain)
    assert delay == 120, f"expected domain override 120ms to beat bucket 800ms, got {delay}ms"


def test_domain_pool_size_overrides_bucket(grpc_client, api, status_client, domain):
    """Explicit domain pool_size wins over the bucket's pool_size."""
    bucket_name = f"bkt-{uuid.uuid4().hex[:6]}"
    r = api.post("/buckets", json={"name": bucket_name, "pool_size": 10})
    bucket_id = r.json()["id"]

    api.post("/domains", json={"name": domain, "bucket_id": bucket_id, "pool_size": 2})

    # Hold 2 permits simultaneously to prove pool_size is honoured
    p1 = grpc_client.acquire(domain)
    p2 = grpc_client.acquire(domain)
    st = get_pool_status(status_client, domain)
    p1.release(200)
    p2.release(200)
    assert st["active"] == 2, f"expected 2 active permits (pool_size=2), got {st['active']}"


# ---------------------------------------------------------------------------
# robots.txt crawl-delay
# ---------------------------------------------------------------------------

def test_robots_txt_override_sets_base_delay(grpc_client, api, status_client, domain):
    """
    A robots.txt override injected via the management API is picked up as
    base_delay_ms when the domain has no explicit delay and no bucket.
    """
    # Inject the robots.txt cache entry via the management API
    r = api.post(f"/robots/{domain}/override", json={"override_delay_ms": 2500})
    assert r.status_code == 200, r.text

    # Domain with no explicit config — robots.txt override should apply
    api.post("/domains", json={"name": domain})

    delay = _read_delay(grpc_client, status_client, domain)
    assert delay == 2500, f"expected robots.txt override 2500ms, got {delay}ms"


def test_domain_explicit_delay_beats_robots_txt(grpc_client, api, status_client, domain):
    """Explicit domain base_delay_ms prevents robots.txt override from applying."""
    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 2500})
    api.post("/domains", json={"name": domain, "base_delay_ms": 75})

    delay = _read_delay(grpc_client, status_client, domain)
    assert delay == 75, f"expected domain override 75ms to beat robots.txt 2500ms, got {delay}ms"


def test_bucket_membership_prevents_robots_txt_applying(grpc_client, api, status_client, domain):
    """
    Having a bucket_id prevents the robots.txt crawl-delay from being used,
    even when the bucket itself has no explicit base_delay_ms.
    """
    api.post(f"/robots/{domain}/override", json={"override_delay_ms": 2500})

    bucket_name = f"bkt-{uuid.uuid4().hex[:6]}"
    r = api.post("/buckets", json={"name": bucket_name})  # no explicit delay
    bucket_id = r.json()["id"]
    api.post("/domains", json={"name": domain, "bucket_id": bucket_id})

    delay = _read_delay(grpc_client, status_client, domain)
    # robots.txt should NOT apply — global default used instead
    assert delay == GLOBAL_DEFAULT_BASE_DELAY_MS, (
        f"expected global default (bucket present blocks robots.txt), got {delay}ms"
    )
