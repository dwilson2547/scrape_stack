from pathlib import Path

from .base import BaseStorage


class LocalStorage(BaseStorage):
    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, content_hash: str, prefix: str | None = None) -> Path:
        base = self.base_path / bucket
        if prefix:
            base = base / prefix
        return base / f"{content_hash}.lz4"

    def write(self, bucket: str, content_hash: str, compressed_data: bytes, prefix: str | None = None) -> None:
        p = self._path(bucket, content_hash, prefix)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(compressed_data)

    def read(self, bucket: str, content_hash: str, prefix: str | None = None) -> bytes:
        p = self._path(bucket, content_hash, prefix)
        if not p.exists():
            raise FileNotFoundError(f"No cache file for {bucket}/{content_hash}")
        return p.read_bytes()

    def delete(self, bucket: str, content_hash: str, prefix: str | None = None) -> None:
        p = self._path(bucket, content_hash, prefix)
        if p.exists():
            p.unlink()

    def exists(self, bucket: str, content_hash: str, prefix: str | None = None) -> bool:
        return self._path(bucket, content_hash, prefix).exists()
