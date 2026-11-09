"""S3 storage integration tests — runs against a live MinIO container.

Skipped automatically when Docker / testcontainers is unavailable.
"""

from __future__ import annotations

import io
import uuid

import pytest

from app.storage.base import make_file_path
from app.storage.s3 import S3Storage

BUCKET = "filecache-s3-test"
EXT = ".zip"
CONTENT = b"S3 integration test content" * 20


def _minio_url(container) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(container.port)
    return f"http://{host}:{port}"


@pytest.fixture()
def store(minio_container):
    return S3Storage(
        bucket=BUCKET,
        endpoint_url=_minio_url(minio_container),
        aws_access_key_id=minio_container.access_key,
        aws_secret_access_key=minio_container.secret_key,
    )


@pytest.fixture()
def h():
    """Unique 64-char hex hash per test so MinIO state never leaks between tests."""
    return uuid.uuid4().hex * 2


def test_s3_write_and_read_roundtrip(store, h):
    store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    f = store.read("docs", None, h, EXT)
    try:
        assert f.read() == CONTENT
    finally:
        f.close()


def test_s3_exists_true_after_write(store, h):
    assert not store.exists("docs", None, h, EXT)
    store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    assert store.exists("docs", None, h, EXT)


def test_s3_get_size(store, h):
    store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    assert store.get_size("docs", None, h, EXT) == len(CONTENT)


def test_s3_delete_removes_file(store, h):
    store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    store.delete("docs", None, h, EXT)
    assert not store.exists("docs", None, h, EXT)


def test_s3_read_byte_range(store, h):
    store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    f = store.read("docs", None, h, EXT, byte_range=(0, 9))
    try:
        data = f.read()
        assert data == CONTENT[:10]
    finally:
        f.close()


def test_s3_write_returns_correct_file_path(store, h):
    fp = store.write("docs", None, h, io.BytesIO(CONTENT), EXT)
    assert fp == make_file_path("docs", None, h, EXT)
