"""Shared pytest fixtures.

Sets up an isolated in-memory SQLite database and temporary local storage
so every test runs completely independently without touching the real filesystem
outside of pytest's tmp_path.
"""

from __future__ import annotations

import os

# Set env vars before any app module is imported so all lazy singletons
# initialise with test values.
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as db_module
import app.request_auth as request_auth_module
import app.metrics as metrics_module
from app.config import Config, IndexConfig, IngestConfig, StorageConfig, LocalStorageConfig
from app.database import Base, get_db
from app.storage import override_storage, reset_storage
from app.storage.local import LocalStorage


# ---------------------------------------------------------------------- #
# Fake request_auth permit + client                                        #
# ---------------------------------------------------------------------- #

class _FakePermit:
    def set_status(self, code: int) -> None:
        pass

    def release(self, code: int | None = None) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeRequestAuthClient:
    def acquire(self, domain: str) -> _FakePermit:
        return _FakePermit()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------- #
# Config helper                                                            #
# ---------------------------------------------------------------------- #

def make_test_config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.index = IndexConfig(db_path=str(tmp_path / "test.db"))
    cfg.storage = StorageConfig(
        backend="local",
        local=LocalStorageConfig(root=str(tmp_path / "storage")),
    )
    cfg.ingest = IngestConfig(temp_dir=str(tmp_path / "tmp"))
    return cfg


# ---------------------------------------------------------------------- #
# Core fixtures                                                            #
# ---------------------------------------------------------------------- #

@pytest.fixture()
def tmp_storage_dir(tmp_path: Path) -> Path:
    d = tmp_path / "storage"
    d.mkdir()
    return d


@pytest.fixture()
def tmp_ingest_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tmp"
    d.mkdir()
    return d


@pytest.fixture()
def app(tmp_storage_dir: Path, tmp_ingest_dir: Path, tmp_path: Path):
    """FastAPI app wired to in-memory SQLite and temporary local storage."""
    from app.config import Config, IndexConfig, IngestConfig, StorageConfig, LocalStorageConfig
    from app.api import create_app

    cfg = make_test_config(tmp_path)

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db_module._engine = test_engine
    db_module._SessionLocal = TestSession

    fastapi_app = create_app(cfg)

    def override_db() -> Generator:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db

    override_storage(LocalStorage(tmp_storage_dir))
    request_auth_module.override_client(FakeRequestAuthClient())

    # Initialise metrics in test mode (no OTLP export, Prometheus re-registered safely)
    metrics_module.init_metrics("filecache-test")

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()
    reset_storage()
    request_auth_module.reset_client()
    metrics_module.shutdown_metrics()
    db_module._engine = None
    db_module._SessionLocal = None


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------- #
# MinIO testcontainer (session-scoped — container starts once per session) #
# ---------------------------------------------------------------------- #

def _minio_endpoint(container) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(container.port)
    return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def minio_container():
    pytest.importorskip("testcontainers.minio")
    from testcontainers.minio import MinioContainer
    with MinioContainer() as minio:
        yield minio


@pytest.fixture()
def s3_app(minio_container, tmp_path: Path, tmp_ingest_dir: Path):
    """FastAPI app wired to in-memory SQLite and a live MinIO S3 bucket."""
    import boto3
    from app.api import create_app
    from app.config import Config, IndexConfig, IngestConfig, StorageConfig, S3Config
    from app.storage.s3 import S3Storage

    endpoint = _minio_endpoint(minio_container)
    bucket_name = "test-filecache"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=minio_container.access_key,
        aws_secret_access_key=minio_container.secret_key,
        region_name="us-east-1",
    )
    try:
        s3.create_bucket(Bucket=bucket_name)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    cfg = Config()
    cfg.index = IndexConfig(db_path=str(tmp_path / "test.db"))
    cfg.storage = StorageConfig(
        backend="s3",
        s3=S3Config(
            endpoint=endpoint,
            access_key=minio_container.access_key,
            secret_key=minio_container.secret_key,
            bucket=bucket_name,
        ),
    )
    cfg.ingest = IngestConfig(temp_dir=str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir(exist_ok=True)

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db_module._engine = test_engine
    db_module._SessionLocal = TestSession

    fastapi_app = create_app(cfg)

    def override_db() -> Generator:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db

    s3_storage = S3Storage(
        bucket=bucket_name,
        endpoint_url=endpoint,
        aws_access_key_id=minio_container.access_key,
        aws_secret_access_key=minio_container.secret_key,
    )
    override_storage(s3_storage)
    request_auth_module.override_client(FakeRequestAuthClient())
    metrics_module.init_metrics("filecache-test-s3")

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()
    reset_storage()
    request_auth_module.reset_client()
    metrics_module.shutdown_metrics()
    db_module._engine = None
    db_module._SessionLocal = None


@pytest.fixture()
def s3_client(s3_app):
    with TestClient(s3_app) as c:
        yield c
