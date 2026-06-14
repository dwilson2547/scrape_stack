from __future__ import annotations

import shutil
from pathlib import Path
from typing import IO

_CHUNK = 1024 * 1024  # 1 MB copy buffer


class _LimitedReader:
    """Wraps an open file to restrict reads to a specific byte window."""

    def __init__(self, f: IO[bytes], length: int) -> None:
        self._f = f
        self._remaining = length

    def read(self, n: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if n < 0 or n > self._remaining:
            n = self._remaining
        data = self._f.read(n)
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "_LimitedReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class LocalVideoStore:
    """Filesystem-backed video store.

    Layout::

        <root>/<bucket>/<prefix>/<hash[:2]>/<hash[2:4]>/<hash><ext>
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> Path:
        base = self.root / bucket / prefix if prefix else self.root / bucket
        return base / hash[:2] / hash[2:4] / f"{hash}{ext}"

    def exists(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> bool:
        return self._path(bucket, prefix, hash, ext).exists()

    def put(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        stream: IO[bytes],
        size: int | None = None,
        ext: str = ".mp4",
    ) -> str:
        dest = self._path(bucket, prefix, hash, ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            shutil.copyfileobj(stream, f, length=_CHUNK)
        return str(dest.relative_to(self.root))

    def get(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        byte_range: tuple[int, int] | None = None,
        ext: str = ".mp4",
    ) -> IO[bytes]:
        path = self._path(bucket, prefix, hash, ext)
        f = open(path, "rb")  # noqa: WPS515 — caller is responsible for close()
        if byte_range is not None:
            start, end = byte_range
            f.seek(start)
            return _LimitedReader(f, end - start + 1)  # type: ignore[return-value]
        return f

    def delete(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> None:
        path = self._path(bucket, prefix, hash, ext)
        if path.exists():
            path.unlink()

    def get_size(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> int:
        return self._path(bucket, prefix, hash, ext).stat().st_size
