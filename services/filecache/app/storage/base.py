from __future__ import annotations

from abc import ABC, abstractmethod
from typing import IO


def make_file_path(bucket: str, prefix: "str | None", content_hash: str, ext: str) -> str:
    """Return the logical file path stored in the DB (same across all backends)."""
    shard_a = content_hash[:2]
    shard_b = content_hash[2:4]
    if prefix:
        clean = "/".join(p for p in prefix.split("/") if p and p not in (".", ".."))
        if clean:
            return f"{bucket}/{clean}/{shard_a}/{shard_b}/{content_hash}{ext}"
    return f"{bucket}/{shard_a}/{shard_b}/{content_hash}{ext}"


class BaseStorage(ABC):
    @abstractmethod
    def write(self, bucket: str, prefix: "str | None", content_hash: str, stream: "IO[bytes]", ext: str) -> str:
        """Write stream to storage. Returns the logical file_path."""

    @abstractmethod
    def read(
        self,
        bucket: str,
        prefix: "str | None",
        content_hash: str,
        ext: str,
        byte_range: "tuple[int, int] | None" = None,
    ) -> "IO[bytes]":
        """Return a readable file-like object.

        byte_range is an inclusive (start, end) pair; None means full file.
        Caller is responsible for closing the returned object.
        """

    @abstractmethod
    def delete(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> None:
        """Delete the stored file. No-op if it does not exist."""

    @abstractmethod
    def exists(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> bool:
        """Return True if the file exists in storage."""

    @abstractmethod
    def get_size(self, bucket: str, prefix: "str | None", content_hash: str, ext: str) -> int:
        """Return the stored file size in bytes."""
