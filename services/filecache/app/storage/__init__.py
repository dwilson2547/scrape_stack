from __future__ import annotations

from .base import BaseStorage

_storage: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage
    if _storage is None:
        raise RuntimeError("Storage not initialised — call init_storage() first")
    return _storage


def init_storage(config) -> None:
    global _storage
    if config.storage.backend == "local":
        if config.storage.local is None:
            raise ValueError("storage.local config required for local backend")
        from .local import LocalStorage
        _storage = LocalStorage(config.storage.local.root)
    elif config.storage.backend == "s3":
        if config.storage.s3 is None:
            raise ValueError("storage.s3 config required for s3 backend")
        s3 = config.storage.s3
        from .s3 import S3Storage
        _storage = S3Storage(
            bucket=s3.bucket,
            endpoint_url=s3.endpoint or None,
            aws_access_key_id=s3.access_key or None,
            aws_secret_access_key=s3.secret_key or None,
            region_name=s3.region,
            multipart_threshold_mb=s3.multipart_threshold_mb,
            multipart_part_size_mb=s3.multipart_part_size_mb,
        )
    else:
        raise ValueError(f"Unknown storage backend: {config.storage.backend!r}")


def override_storage(instance: BaseStorage) -> None:
    global _storage
    _storage = instance


def reset_storage() -> None:
    global _storage
    _storage = None
