from __future__ import annotations

from .base import VideoStore

_store: VideoStore | None = None


def get_storage() -> VideoStore:
    if _store is None:
        raise RuntimeError("Storage not initialized — call init_storage() first")
    return _store


def init_storage(config) -> None:
    """Initialise storage from the application Config object."""
    global _store
    backend = config.video_store.backend
    if backend == "local":
        if config.video_store.local is None:
            raise ValueError("video_store.local config required for local backend")
        from .local import LocalVideoStore
        _store = LocalVideoStore(config.video_store.local.root)
    elif backend == "s3":
        if config.video_store.s3 is None:
            raise ValueError("video_store.s3 config required for s3 backend")
        s3 = config.video_store.s3
        from .s3 import S3VideoStore
        _store = S3VideoStore(
            endpoint=s3.endpoint,
            access_key=s3.access_key,
            secret_key=s3.secret_key,
            region=s3.region,
            multipart_threshold_mb=config.dedup.multipart_threshold_mb,
            multipart_part_size_mb=config.dedup.multipart_part_size_mb,
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend!r}")


def override_storage(store: VideoStore) -> None:
    global _store
    _store = store


def reset_storage() -> None:
    global _store
    _store = None
