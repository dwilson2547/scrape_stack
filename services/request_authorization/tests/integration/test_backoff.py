"""
Adaptive backoff tests.

Strategy: use the /status endpoint to read current_delay_ms directly rather
than relying on wall-clock timing. Each subsequent acquire() acts as a
synchronization barrier — it doesn't return until the AfterFunc (which fires
after the backoff delay) has served it, so the BackoffState is fully updated
by the time we query the status.

Domain config for all tests in this file:
  pool_size=1, base_delay_ms=50, backoff_multiplier=3.0,
  max_delay_ms=500, recovery_threshold=3
"""

import pytest

from conftest import get_pool_status

DOMAIN_CONFIG = {
    "pool_size": 1,
    "base_delay_ms": 50,
    "backoff_multiplier": 3.0,
    "max_delay_ms": 500,
    "recovery_threshold": 3,
}


@pytest.fixture
def backoff_domain(api, domain):
    api.post("/domains", json={"name": domain, **DOMAIN_CONFIG})
    return domain


def _acquire_release(client, domain, status_code: int):
    """Helper: hold one permit then release it with the given status."""
    p = client.acquire(domain)
    p.release(status_code)


def _sync_and_check(grpc_client, status_client, domain) -> int:
    """
    Acquire a permit (blocks until previous backoff timer fires), read
    current_delay_ms, then release with status 0.

    Status 0 is neutral: it's not ≥200 and not 429, so BackoffState.Record()
    is a no-op. This prevents sync calls from accidentally advancing the
    consecutive-2xx counter and triggering early recovery.
    """
    p = grpc_client.acquire(domain)
    st = get_pool_status(status_client, domain)
    delay = st["current_delay_ms"]
    p.release(0)
    return delay


def test_base_delay_after_200(grpc_client, status_client, backoff_domain):
    """200 response keeps the delay at base_delay_ms."""
    _acquire_release(grpc_client, backoff_domain, 200)
    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    assert delay == 50, f"expected base delay 50ms after 200, got {delay}ms"


def test_429_multiplies_delay(grpc_client, status_client, backoff_domain):
    """Single 429 multiplies the delay by backoff_multiplier (50 → 150)."""
    _acquire_release(grpc_client, backoff_domain, 429)
    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    assert delay == 150, f"expected 150ms after first 429, got {delay}ms"


def test_repeated_429s_grow_delay(grpc_client, status_client, backoff_domain):
    """Consecutive 429s keep multiplying: 50 → 150 → 450."""
    _acquire_release(grpc_client, backoff_domain, 429)
    _sync_and_check(grpc_client, status_client, backoff_domain)  # absorb first step

    _acquire_release(grpc_client, backoff_domain, 429)
    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    assert delay == 450, f"expected 450ms after second 429, got {delay}ms"


def test_delay_capped_at_max_delay_ms(grpc_client, status_client, backoff_domain):
    """Delay never exceeds max_delay_ms (500ms) regardless of 429 count."""
    # Three 429s: 50 → 150 → 450 → 1350 (capped at 500)
    for _ in range(3):
        _acquire_release(grpc_client, backoff_domain, 429)
        _sync_and_check(grpc_client, status_client, backoff_domain)

    _acquire_release(grpc_client, backoff_domain, 429)
    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    assert delay == 500, f"expected delay capped at 500ms, got {delay}ms"


def test_2xx_streak_recovers_delay(grpc_client, status_client, backoff_domain):
    """
    After recovery_threshold (3) consecutive 2xx responses the delay resets
    to base_delay_ms regardless of how high it climbed.
    """
    # Drive delay up first
    _acquire_release(grpc_client, backoff_domain, 429)
    _acquire_release(grpc_client, backoff_domain, 429)
    _sync_and_check(grpc_client, status_client, backoff_domain)  # consume 2nd 429 grant

    # Now send recovery_threshold 200s (each acquire/release is one 200 cycle)
    for _ in range(DOMAIN_CONFIG["recovery_threshold"]):
        _acquire_release(grpc_client, backoff_domain, 200)

    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    assert delay == 50, f"expected delay recovered to 50ms, got {delay}ms"


def test_429_resets_2xx_streak(grpc_client, status_client, backoff_domain):
    """A 429 in the middle of a 2xx streak resets the consecutive counter."""
    _acquire_release(grpc_client, backoff_domain, 429)  # drive delay to 150ms
    _sync_and_check(grpc_client, status_client, backoff_domain)

    # Two 200s (streak = 2, threshold = 3 — not yet recovered)
    _acquire_release(grpc_client, backoff_domain, 200)
    _acquire_release(grpc_client, backoff_domain, 200)
    _acquire_release(grpc_client, backoff_domain, 429)  # resets streak
    delay = _sync_and_check(grpc_client, status_client, backoff_domain)
    # 429 applied to 150ms → 450ms
    assert delay == 450, f"expected streak reset → 450ms, got {delay}ms"
