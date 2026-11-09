"""Unit tests for LocalVideoStore."""
from __future__ import annotations

import io

import pytest

from app.storage.local import LocalVideoStore

BUCKET = "test"
PREFIX = ""
HASH = "a" * 64
EXT = ".mp4"
CONTENT = b"fake video content for storage tests" * 50


@pytest.fixture()
def store(tmp_path):
    return LocalVideoStore(tmp_path / "store")


# ---------------------------------------------------------------------- #
# Basic contract                                                            #
# ---------------------------------------------------------------------- #

def test_put_and_get_roundtrip(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    f = store.get(BUCKET, PREFIX, HASH, ext=EXT)
    try:
        assert f.read() == CONTENT
    finally:
        f.close()


def test_put_returns_relative_path(store):
    path = store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    assert BUCKET in path
    assert HASH in path
    assert EXT in path


def test_exists_false_before_put(store):
    assert not store.exists(BUCKET, PREFIX, HASH, EXT)


def test_exists_true_after_put(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    assert store.exists(BUCKET, PREFIX, HASH, EXT)


def test_get_size(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    assert store.get_size(BUCKET, PREFIX, HASH, EXT) == len(CONTENT)


def test_delete_removes_file(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    store.delete(BUCKET, PREFIX, HASH, EXT)
    assert not store.exists(BUCKET, PREFIX, HASH, EXT)


def test_delete_nonexistent_is_noop(store):
    store.delete(BUCKET, PREFIX, HASH, EXT)  # must not raise


# ---------------------------------------------------------------------- #
# Byte-range reads                                                          #
# ---------------------------------------------------------------------- #

def test_get_byte_range(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    f = store.get(BUCKET, PREFIX, HASH, byte_range=(0, 9), ext=EXT)
    try:
        assert f.read() == CONTENT[:10]
    finally:
        f.close()


def test_get_byte_range_mid(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    f = store.get(BUCKET, PREFIX, HASH, byte_range=(10, 19), ext=EXT)
    try:
        assert f.read() == CONTENT[10:20]
    finally:
        f.close()


def test_get_byte_range_partial_reads(store):
    store.put(BUCKET, PREFIX, HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    f = store.get(BUCKET, PREFIX, HASH, byte_range=(0, 29), ext=EXT)
    try:
        chunk1 = f.read(10)
        chunk2 = f.read(10)
        chunk3 = f.read(10)
        chunk4 = f.read(10)  # past end — should be empty
        assert chunk1 == CONTENT[:10]
        assert chunk2 == CONTENT[10:20]
        assert chunk3 == CONTENT[20:30]
        assert chunk4 == b""
    finally:
        f.close()


# ---------------------------------------------------------------------- #
# Layout                                                                    #
# ---------------------------------------------------------------------- #

def test_no_prefix_sharding_layout(store, tmp_path):
    """Without prefix: store/bucket/hash[:2]/hash[2:4]/hash.ext"""
    store.put(BUCKET, "", HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    expected = tmp_path / "store" / BUCKET / HASH[:2] / HASH[2:4] / f"{HASH}{EXT}"
    assert expected.exists()


def test_prefix_sharding_layout(store, tmp_path):
    """With prefix: store/bucket/prefix/hash[:2]/hash[2:4]/hash.ext"""
    store.put(BUCKET, "run1/batch2", HASH, io.BytesIO(CONTENT), len(CONTENT), EXT)
    expected = (
        tmp_path / "store" / BUCKET / "run1" / "batch2"
        / HASH[:2] / HASH[2:4] / f"{HASH}{EXT}"
    )
    assert expected.exists()


def test_different_buckets_isolated(store):
    h = "b" * 64
    store.put("bucket-a", "", h, io.BytesIO(b"aaa"), 3, EXT)
    store.put("bucket-b", "", h, io.BytesIO(b"bbb"), 3, EXT)
    fa = store.get("bucket-a", "", h, ext=EXT)
    fb = store.get("bucket-b", "", h, ext=EXT)
    try:
        assert fa.read() == b"aaa"
        assert fb.read() == b"bbb"
    finally:
        fa.close()
        fb.close()
