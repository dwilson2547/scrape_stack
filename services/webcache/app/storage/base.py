from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def write(self, bucket: str, content_hash: str, compressed_data: bytes, prefix: str | None = None) -> None:
        """Write compressed page data."""

    @abstractmethod
    def read(self, bucket: str, content_hash: str, prefix: str | None = None) -> bytes:
        """Return compressed bytes. Raise FileNotFoundError if absent."""

    @abstractmethod
    def delete(self, bucket: str, content_hash: str, prefix: str | None = None) -> None:
        """Delete stored file. No-op if it doesn't exist."""

    @abstractmethod
    def exists(self, bucket: str, content_hash: str, prefix: str | None = None) -> bool:
        """Return True if a file for bucket/[prefix/]content_hash exists."""
