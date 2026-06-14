import pytest
from app.storage.local import LocalStorage


def test_write_read_roundtrip(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.write("abc123", b"hello world")
    assert s.read("abc123") == b"hello world"


def test_exists_true(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.write("key1", b"data")
    assert s.exists("key1") is True


def test_exists_false(tmp_path):
    s = LocalStorage(str(tmp_path))
    assert s.exists("nonexistent") is False


def test_read_missing_raises(tmp_path):
    s = LocalStorage(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        s.read("missing")


def test_delete_removes(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.write("key2", b"data")
    s.delete("key2")
    assert s.exists("key2") is False


def test_delete_noop_when_missing(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.delete("does_not_exist")


def test_directory_created_on_init(tmp_path):
    new_dir = tmp_path / "newdir"
    s = LocalStorage(str(new_dir))
    assert new_dir.exists()


def test_file_named_by_hash(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.write("myhash", b"content")
    assert (tmp_path / "myhash").exists()
