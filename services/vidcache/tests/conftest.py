"""Shared pytest fixtures for vidcache."""
from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as db_module
import app.request_auth as request_auth_module
from app.api import create_app
from app.config import Config, DedupConfig, IndexConfig, IngestConfig, LocalStoreConfig, VideoStoreConfig
from app.database import Base, get_db
from app.storage import override_storage, reset_storage
from app.storage.local import LocalVideoStore


class _FakePermit:
    def release(self, code: int | None = None) -> None:
        pass


class FakeRequestAuthClient:
    def acquire(self, domain: str) -> _FakePermit:
        return _FakePermit()

    def close(self) -> None:
        pass


def make_config(tmp_path: Path) -> Config:
    (tmp_path / "tmp").mkdir()
    (tmp_path / "storage").mkdir()
    return Config(
        video_store=VideoStoreConfig(
            backend="local",
            local=LocalStoreConfig(root=str(tmp_path / "storage")),
        ),
        dedup=DedupConfig(phash_threshold=10),
        ingest=IngestConfig(temp_dir=str(tmp_path / "tmp")),
        index=IndexConfig(db_path=str(tmp_path / "test.db")),
    )


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    return make_config(tmp_path)


@pytest.fixture()
def client(config: Config, tmp_path: Path):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    db_module._engine = test_engine
    db_module._SessionLocal = TestSession

    fastapi_app = create_app(config)

    def override_db() -> Generator:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db

    override_storage(LocalVideoStore(tmp_path / "storage"))
    request_auth_module.override_client(FakeRequestAuthClient())

    with TestClient(fastapi_app) as c:
        yield c

    fastapi_app.dependency_overrides.clear()
    reset_storage()
    request_auth_module.reset_client()
    db_module._engine = None
    db_module._SessionLocal = None
