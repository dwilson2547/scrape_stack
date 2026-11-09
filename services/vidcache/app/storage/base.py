from __future__ import annotations

from typing import IO, Protocol, runtime_checkable


@runtime_checkable
class VideoStore(Protocol):
    def exists(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> bool: ...

    def put(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        stream: IO[bytes],
        size: int | None = None,
        ext: str = ".mp4",
    ) -> str:
        """Write *stream* to the store and return the logical file path."""
        ...

    def get(
        self,
        bucket: str,
        prefix: str,
        hash: str,
        byte_range: tuple[int, int] | None = None,
        ext: str = ".mp4",
    ) -> IO[bytes]:
        """Return a readable IO[bytes] for the video.

        If *byte_range* is (start, end) (both inclusive), only those bytes are
        returned — mirroring S3 Range semantics.
        """
        ...

    def delete(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> None: ...

    def get_size(self, bucket: str, prefix: str, hash: str, ext: str = ".mp4") -> int: ...
