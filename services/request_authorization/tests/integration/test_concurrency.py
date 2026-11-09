"""
Concurrent-client throughput and pool-enforcement tests.

The key scenario: pool_size=3, base_delay_ms=500ms (flat — multiplier=1.0,
max=base, recovery_threshold=999 to keep delay constant throughout).

12 clients all start simultaneously. With pool_size=3 the server hands out
permits in batches of 3. After each batch returns, a 500ms AfterFunc fires
before the next batch is served. The first batch is granted immediately
(available=3 on a fresh pool), so there are exactly 3 inter-batch waits.

Expected wall-clock time: 3 × 500ms + (4 × round-trip overhead) ≈ 1.5–2.5s
"""

import threading
import time
import uuid

import httpx
import pytest

from conftest import get_pool_status

N_CLIENTS = 12
POOL_SIZE = 3
DELAY_MS = 500
N_BATCHES = N_CLIENTS // POOL_SIZE   # 4

EXPECTED_MIN_S = (N_BATCHES - 1) * DELAY_MS / 1000 * 0.7   # 1.05s
EXPECTED_MAX_S = (N_BATCHES - 1) * DELAY_MS / 1000 * 2.5 + 2.0  # generous ceiling


@pytest.fixture
def throughput_domain(api, domain):
    api.post("/domains", json={
        "name": domain,
        "pool_size": POOL_SIZE,
        "base_delay_ms": DELAY_MS,
        "backoff_multiplier": 1.0,
        "max_delay_ms": DELAY_MS,
        "recovery_threshold": 999,
    })
    return domain


def test_all_clients_complete_without_deadlock(grpc_client, test_svc, throughput_domain):
    """All 12 concurrent clients eventually receive and return their permits."""
    errors: list[Exception] = []
    completed = []
    lock = threading.Lock()

    def worker():
        try:
            with grpc_client.acquire(throughput_domain) as permit:
                r = test_svc.get("/probe/200", timeout=10.0)
                permit.set_status(r.status_code)
            with lock:
                completed.append(1)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(N_CLIENTS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60.0)

    assert not errors, f"worker errors: {errors}"
    assert len(completed) == N_CLIENTS, f"only {len(completed)}/{N_CLIENTS} clients completed"


def test_pool_size_enforced_under_concurrency(grpc_client, test_svc, throughput_domain):
    """At most pool_size permits are held simultaneously at any point."""
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()
    errors: list[Exception] = []

    def worker():
        nonlocal in_flight, max_in_flight
        try:
            permit = grpc_client.acquire(throughput_domain)
            with lock:
                in_flight += 1
                if in_flight > max_in_flight:
                    max_in_flight = in_flight
            r = test_svc.get("/probe/200", timeout=10.0)
            with lock:
                in_flight -= 1
            permit.release(r.status_code)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(N_CLIENTS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60.0)

    assert not errors, f"worker errors: {errors}"
    assert max_in_flight <= POOL_SIZE, (
        f"pool_size={POOL_SIZE} violated: {max_in_flight} permits held simultaneously"
    )


def test_throughput_timing_matches_batched_rate_limit(grpc_client, test_svc, throughput_domain):
    """
    Wall-clock time for 12 clients to complete should match the expected
    batched-rate formula:

      (N_BATCHES - 1) × delay_ms  ≈  3 × 500ms = 1500ms

    (First batch is granted immediately from the available pool; subsequent
    batches each wait one delay period for their AfterFunc to fire.)

    Bounds: [{EXPECTED_MIN_S:.2f}s, {EXPECTED_MAX_S:.2f}s]
    """
    barrier = threading.Barrier(N_CLIENTS)  # all start at the same instant
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait(timeout=10.0)
            with grpc_client.acquire(throughput_domain) as permit:
                r = test_svc.get("/probe/200", timeout=10.0)
                permit.set_status(r.status_code)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(N_CLIENTS)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60.0)
    elapsed = time.monotonic() - t0

    assert not errors, f"worker errors: {errors}"
    assert EXPECTED_MIN_S <= elapsed <= EXPECTED_MAX_S, (
        f"throughput timing out of range: {elapsed:.3f}s "
        f"(expected {EXPECTED_MIN_S:.2f}–{EXPECTED_MAX_S:.2f}s for "
        f"{N_CLIENTS} clients, pool_size={POOL_SIZE}, delay={DELAY_MS}ms)"
    )


def test_isolated_domains_do_not_interfere(grpc_client, api):
    """Permits on domain A and domain B are fully independent."""
    domain_a = f"iso-a-{uuid.uuid4().hex[:8]}.local"
    domain_b = f"iso-b-{uuid.uuid4().hex[:8]}.local"

    for d in (domain_a, domain_b):
        api.post("/domains", json={"name": d, "pool_size": 1, "base_delay_ms": 0})

    # Exhaust domain_a (pool_size=1)
    pa = grpc_client.acquire(domain_a)

    # domain_b should be immediately available despite domain_a being full
    done = threading.Event()

    def acquire_b():
        pb = grpc_client.acquire(domain_b)
        pb.release(200)
        done.set()

    t = threading.Thread(target=acquire_b, daemon=True)
    t.start()
    acquired_b = done.wait(timeout=3.0)

    pa.release(200)
    t.join(timeout=5.0)

    assert acquired_b, "domain_b permit was blocked by domain_a being full — pools are not isolated"
