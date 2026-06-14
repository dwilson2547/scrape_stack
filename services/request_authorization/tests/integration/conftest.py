"""
Session fixtures for the request-auth integration test suite.

Stack: Go gRPC server (9000/9003) + FastAPI management API (9001) + HTTP test service (9004).
All services are started once per test session via docker compose.

Each test gets a unique domain name from the `domain` fixture so every test
works with a fresh pool — no container restarts needed between tests.
"""

import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from request_auth_client import RequestAuthClient

COMPOSE_FILE = Path(__file__).parent / "docker-compose.yaml"
PROJECT_NAME = "request-auth-test"

GRPC_ADDR = "localhost:9000"
API_BASE = "http://localhost:9001/api"
STATUS_BASE = "http://localhost:9003"
TEST_SVC_BASE = "http://localhost:9004"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for(url: str, label: str, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(2.0)
    raise RuntimeError(f"{label} at {url} not ready after {timeout:.0f}s")


def get_pool_status(status_client: httpx.Client, domain_name: str) -> dict | None:
    """Return the pool-status snapshot for domain_name, or None if no pool exists yet."""
    r = status_client.get("/status")
    r.raise_for_status()
    return next((p for p in r.json().get("pools", []) if p["domain"] == domain_name), None)


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def docker_stack():
    """Spin up the full test stack once per session, tear it down on exit."""
    base_cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT_NAME]

    # Clean up any leftover containers from a previous run
    subprocess.run(base_cmd + ["down", "-v", "--remove-orphans"], check=False,
                   capture_output=True)

    subprocess.run(
        base_cmd + ["up", "--build", "--force-recreate", "-d"],
        check=True,
    )

    try:
        _wait_for(f"{STATUS_BASE}/health",  "gRPC server")
        _wait_for(f"{API_BASE[:-4]}/health", "management API")  # strip /api suffix
        _wait_for(f"{TEST_SVC_BASE}/healthz", "HTTP test service")
        yield
    finally:
        subprocess.run(base_cmd + ["down", "-v"], check=False)


@pytest.fixture(scope="session")
def grpc_client(docker_stack) -> RequestAuthClient:
    client = RequestAuthClient(GRPC_ADDR)
    yield client
    client.close()


@pytest.fixture(scope="session")
def api(docker_stack) -> httpx.Client:
    with httpx.Client(base_url=API_BASE, timeout=10.0) as c:
        yield c


@pytest.fixture(scope="session")
def status_client(docker_stack) -> httpx.Client:
    with httpx.Client(base_url=STATUS_BASE, timeout=5.0) as c:
        yield c


@pytest.fixture(scope="session")
def test_svc(docker_stack) -> httpx.Client:
    with httpx.Client(base_url=TEST_SVC_BASE, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def domain() -> str:
    """Unique domain name per test — gives every test a fresh pool."""
    return f"test-{uuid.uuid4().hex[:10]}.local"
