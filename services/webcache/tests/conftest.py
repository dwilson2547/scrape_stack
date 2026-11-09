"""
Shared pytest fixtures.

The module-level ``test_app`` / ``client`` fixtures stand up an in-memory
SQLite database and a temporary local storage directory so every test
runs in full isolation without touching the filesystem outside of tmp.
"""

import os

# Set these before any app modules are imported so pydantic-settings picks them up.
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/webcache_test")

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def tmp_storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture()
def app(tmp_storage_dir: Path):
    """
    Return a FastAPI app wired to an in-memory SQLite DB and a temporary
    local storage directory.
    """
    import app.database as db_module
    from sqlalchemy.pool import StaticPool

    from app.database import Base, get_db
    from app.main import app as fastapi_app
    from app.storage import override_storage, reset_storage
    from app.storage.local import LocalStorage

    # In-memory SQLite engine shared across all connections via StaticPool
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Patch the lazy singletons so the lifespan's create_all also targets the test DB
    db_module._engine = test_engine
    db_module._SessionLocal = TestSession

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db
    override_storage(LocalStorage(tmp_storage_dir))

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()
    reset_storage()
    # Reset lazy singletons so the next test gets a fresh DB
    db_module._engine = None
    db_module._SessionLocal = None


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# MinIO testcontainer (session-scoped so the container starts once)
# ---------------------------------------------------------------------------

def _minio_endpoint(container) -> str:
    cfg = container.get_config()
    return f"http://{cfg['endpoint']}"


@pytest.fixture(scope="session")
def minio_container():
    """Start a MinIO container for the session. Requires Docker."""
    pytest.importorskip("testcontainers.minio")
    from testcontainers.minio import MinioContainer

    with MinioContainer() as minio:
        yield minio


@pytest.fixture()
def s3_app(minio_container, tmp_path: Path):
    """
    Return a FastAPI app wired to an in-memory SQLite DB and a MinIO-backed
    S3 storage.
    """
    import boto3
    from sqlalchemy.pool import StaticPool

    from app.database import Base, get_db
    from app.main import app as fastapi_app
    from app.storage import override_storage, reset_storage
    from app.storage.s3 import S3Storage

    bucket = "test-webcache"
    endpoint = _minio_endpoint(minio_container)
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=minio_container.access_key,
        aws_secret_access_key=minio_container.secret_key,
        region_name="us-east-1",
    )
    try:
        s3.create_bucket(Bucket=bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    # Patch settings so S3Storage picks up the test MinIO instance
    import app.config as cfg_module

    original = cfg_module.settings
    cfg_module.settings = cfg_module.Settings(
        storage_backend="s3",
        s3_bucket=bucket,
        s3_endpoint_url=endpoint,
        aws_access_key_id=minio_container.access_key,
        aws_secret_access_key=minio_container.secret_key,
    )

    storage = S3Storage()
    # Patch storage settings on the already-created instance
    storage._bucket = bucket
    storage._client = s3

    import app.database as db_module

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db_module._engine = test_engine
    db_module._SessionLocal = TestSession

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db
    override_storage(storage)

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()
    reset_storage()
    db_module._engine = None
    db_module._SessionLocal = None
    cfg_module.settings = original


@pytest.fixture()
def s3_client(s3_app):
    with TestClient(s3_app) as c:
        yield c
