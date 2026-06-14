"""
End-to-end permit lifecycle tests.

Covers: acquire → HTTP request → release, context-manager variants,
idempotent double-release, and domain registration side-effect.
"""

import time

from conftest import get_pool_status


def test_explicit_acquire_release(grpc_client, test_svc, domain):
    """acquire → real HTTP call → explicit release round-trips cleanly."""
    permit = grpc_client.acquire(domain)
    r = test_svc.get("/probe/200")
    permit.release(r.status_code)
    assert r.status_code == 200


def test_context_manager_success(grpc_client, test_svc, domain):
    """Context manager auto-releases with the status set inside the block."""
    with grpc_client.acquire(domain) as permit:
        r = test_svc.get("/probe/200")
        permit.set_status(r.status_code)


def test_context_manager_releases_on_exception(grpc_client, domain):
    """Context manager releases with status 0 when an exception escapes the block."""
    try:
        with grpc_client.acquire(domain) as permit:  # noqa: F841
            raise RuntimeError("simulated scraper error")
    except RuntimeError:
        pass
    # If the permit was NOT released the pool would be exhausted and the next
    # acquire (for this same domain, pool_size=1 by default) would block forever.
    # Getting here proves it was released.
    p2 = grpc_client.acquire(domain)
    p2.release(200)


def test_double_release_is_idempotent(grpc_client, domain):
    permit = grpc_client.acquire(domain)
    permit.release(200)
    permit.release(200)  # second call must not raise or hang
    # Acquire again to prove the pool is not in a broken state
    p2 = grpc_client.acquire(domain)
    p2.release(200)


def test_domain_registered_after_first_request(grpc_client, api, domain):
    """First gRPC request triggers async domain row insertion via initDomain()."""
    p = grpc_client.acquire(domain)
    p.release(0)
    time.sleep(1.0)  # allow async initDomain goroutine to complete
    names = [d["name"] for d in api.get("/domains").json()]
    assert domain in names, f"{domain!r} not found in management API domains list"


def test_pool_appears_in_status_after_first_acquire(grpc_client, status_client, domain):
    """A pool entry appears in the /status endpoint once a permit has been acquired."""
    p = grpc_client.acquire(domain)
    st = get_pool_status(status_client, domain)
    assert st is not None, f"no pool status found for {domain!r}"
    assert st["active"] == 1
    assert st["queued"] == 0
    p.release(200)
