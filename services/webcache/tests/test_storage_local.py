"""Tests for LocalStorage backend in isolation."""

import lz4.frame
import pytest

from app.storage.local import LocalStorage

BUCKET = "testbucket"
HASH = "a" * 64


@pytest.fixture()
def storage(tmp_path):
    return LocalStorage(tmp_path / "cache")


def _compress(text: str) -> bytes:
    return lz4.frame.compress(text.encode())


class TestLocalStorage:
    def test_write_and_read(self, storage):
        data = _compress("hello world")
        storage.write(BUCKET, HASH, data)
        assert storage.read(BUCKET, HASH) == data

    def test_exists_true(self, storage):
        storage.write(BUCKET, HASH, _compress("data"))
        assert storage.exists(BUCKET, HASH) is True

    def test_exists_false(self, storage):
        assert storage.exists(BUCKET, "doesnotexist" + "x" * 52) is False

    def test_read_missing_raises(self, storage):
        with pytest.raises(FileNotFoundError):
            storage.read(BUCKET, HASH)

    def test_delete_removes_file(self, storage):
        storage.write(BUCKET, HASH, _compress("data"))
        storage.delete(BUCKET, HASH)
        assert storage.exists(BUCKET, HASH) is False

    def test_delete_noop_when_missing(self, storage):
        storage.delete(BUCKET, HASH)  # should not raise

    def test_creates_directory_on_init(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        s = LocalStorage(deep)
        assert deep.exists()

    def test_file_path_without_prefix(self, tmp_path):
        s = LocalStorage(tmp_path / "cache")
        s.write(BUCKET, HASH, _compress("x"))
        assert (tmp_path / "cache" / BUCKET / f"{HASH}.lz4").exists()

    def test_file_path_with_prefix(self, tmp_path):
        s = LocalStorage(tmp_path / "cache")
        s.write(BUCKET, HASH, _compress("x"), prefix="run1/batch2")
        assert (tmp_path / "cache" / BUCKET / "run1" / "batch2" / f"{HASH}.lz4").exists()

    def test_prefix_isolates_reads(self, storage):
        data_a = _compress("content a")
        data_b = _compress("content b")
        storage.write(BUCKET, HASH, data_a, prefix="run1")
        storage.write(BUCKET, HASH, data_b, prefix="run2")
        assert storage.read(BUCKET, HASH, prefix="run1") == data_a
        assert storage.read(BUCKET, HASH, prefix="run2") == data_b
