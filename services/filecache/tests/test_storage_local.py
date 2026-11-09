"""Unit tests for LocalStorage — exercises write/read/exists/delete contract."""

from __future__ import annotations

import io
import pytest

from app.storage.local import LocalStorage
from app.storage.base import make_file_path

BUCKET = "test"
HASH = "a" * 64
EXT = ".pdf"
CONTENT = b"local storage test content" * 10


@pytest.fixture()
def store(tmp_path):
    return LocalStorage(tmp_path / "store")


def test_write_and_read_roundtrip(store):
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    f = store.read(BUCKET, None, HASH, EXT)
    try:
        assert f.read() == CONTENT
    finally:
        f.close()


def test_write_returns_correct_file_path(store):
    fp = store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    assert fp == make_file_path(BUCKET, None, HASH, EXT)


def test_exists_true_after_write(store):
    assert not store.exists(BUCKET, None, HASH, EXT)
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    assert store.exists(BUCKET, None, HASH, EXT)


def test_get_size(store):
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    assert store.get_size(BUCKET, None, HASH, EXT) == len(CONTENT)


def test_delete_removes_file(store):
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    store.delete(BUCKET, None, HASH, EXT)
    assert not store.exists(BUCKET, None, HASH, EXT)


def test_delete_nonexistent_is_noop(store):
    store.delete(BUCKET, None, HASH, EXT)  # should not raise


def test_read_missing_raises(store):
    with pytest.raises(FileNotFoundError):
        store.read(BUCKET, None, HASH, EXT)


def test_read_byte_range(store):
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    f = store.read(BUCKET, None, HASH, EXT, byte_range=(0, 9))
    try:
        data = f.read()
        assert data == CONTENT[:10]
    finally:
        f.close()


def test_read_byte_range_mid(store):
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    f = store.read(BUCKET, None, HASH, EXT, byte_range=(5, 14))
    try:
        data = f.read()
        assert data == CONTENT[5:15]
    finally:
        f.close()


def test_read_byte_range_partial_reads(store):
    """LimitedReader should honour partial read() calls."""
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    f = store.read(BUCKET, None, HASH, EXT, byte_range=(0, 19))
    try:
        chunk1 = f.read(10)
        chunk2 = f.read(10)
        chunk3 = f.read(10)  # should be empty
        assert chunk1 == CONTENT[:10]
        assert chunk2 == CONTENT[10:20]
        assert chunk3 == b""
    finally:
        f.close()


def test_sharding_layout(store, tmp_path):
    """Files are stored under bucket/hash[:2]/hash[2:4]/hash.ext (no prefix)."""
    store.write(BUCKET, None, HASH, io.BytesIO(CONTENT), EXT)
    expected = tmp_path / "store" / BUCKET / HASH[:2] / HASH[2:4] / f"{HASH}{EXT}"
    assert expected.exists()


def test_prefix_sharding_layout(store, tmp_path):
    """Prefix inserts an extra path segment: bucket/prefix/hash[:2]/hash[2:4]/hash.ext."""
    store.write(BUCKET, "run1/batch2", HASH, io.BytesIO(CONTENT), EXT)
    expected = tmp_path / "store" / BUCKET / "run1" / "batch2" / HASH[:2] / HASH[2:4] / f"{HASH}{EXT}"
    assert expected.exists()


def test_prefix_roundtrip(store):
    store.write(BUCKET, "jobs/scrape", HASH, io.BytesIO(CONTENT), EXT)
    f = store.read(BUCKET, "jobs/scrape", HASH, EXT)
    try:
        assert f.read() == CONTENT
    finally:
        f.close()


def test_prefix_isolation(store):
    """Same hash under different prefixes are independent files."""
    h = "c" * 64
    store.write(BUCKET, "prefix-a", h, io.BytesIO(b"alpha"), EXT)
    store.write(BUCKET, "prefix-b", h, io.BytesIO(b"beta"), EXT)
    fa = store.read(BUCKET, "prefix-a", h, EXT)
    fb = store.read(BUCKET, "prefix-b", h, EXT)
    try:
        assert fa.read() == b"alpha"
        assert fb.read() == b"beta"
    finally:
        fa.close()
        fb.close()


def test_multiple_buckets_isolated(store):
    """Files in different buckets with the same hash coexist independently."""
    h = "b" * 64
    store.write("bucket-a", None, h, io.BytesIO(b"bucket a"), ".txt")
    store.write("bucket-b", None, h, io.BytesIO(b"bucket b"), ".txt")
    fa = store.read("bucket-a", None, h, ".txt")
    fb = store.read("bucket-b", None, h, ".txt")
    try:
        assert fa.read() == b"bucket a"
        assert fb.read() == b"bucket b"
    finally:
        fa.close()
        fb.close()
