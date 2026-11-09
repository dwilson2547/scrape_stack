from __future__ import annotations

from pathlib import Path
from typing import IO

from .base import BaseStorage, make_file_path


class _LimitedReader:
    """Wraps a file object and limits reads to a fixed byte count."""

    def __init__(self, f: IO[bytes], limit: int) -> None:
        self._f = f
        self._remaining = limit

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        chunk = self._f.read(size)
        self._remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "_LimitedReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class LocalStorage(BaseStorage):
    def __init__(self, root: "str | Path") -> None:
        self._root = Path(root)

    def _path(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> Path:
        return self._root / make_file_path(bucket, prefix, content_hash, ext)

    def write(self, bucket: str, prefix: "str | None", content_hash: str, stream: IO[bytes], ext: str) -> str:
        dest = self._path(bucket, prefix, content_hash, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            while chunk := stream.read(1024 * 1024):
                f.write(chunk)
        return make_file_path(bucket, prefix, content_hash, ext)

    def read(
        self,
        bucket: str,
        prefix: "str | None",
        content_hash: str,
        ext: str,
        byte_range: "tuple[int, int] | None" = None,
    ) -> IO[bytes]:
        path = self._path(bucket, prefix, content_hash, ext)
        if not path.exists():
            raise FileNotFoundError(f"No stored file at {path}")
        f = open(path, "rb")
        if byte_range is not None:
            start, end = byte_range
            f.seek(start)
            return _LimitedReader(f, end - start + 1)  # type: ignore[return-value]
        return f

    def delete(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> None:
        path = self._path(bucket, prefix, content_hash, ext)
        path.unlink(missing_ok=True)

    def exists(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> bool:
        return self._path(bucket, prefix, content_hash, ext).exists()

    def get_size(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> int:
        return self._path(bucket, prefix, content_hash, ext).stat().st_size
