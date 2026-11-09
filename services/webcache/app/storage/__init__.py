from ..config import StorageBackend, settings
from .base import BaseStorage

_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    """Return the singleton storage backend. Lazily initialized."""
    global _instance
    if _instance is None:
        if settings.storage_backend == StorageBackend.local:
            from .local import LocalStorage

            _instance = LocalStorage(settings.local_storage_path)
        else:
            from .s3 import S3Storage

            _instance = S3Storage()
    return _instance


def override_storage(backend: BaseStorage) -> None:
    """Replace the singleton — used in tests."""
    global _instance
    _instance = backend


def reset_storage() -> None:
    """Clear the singleton so it is re-created on next call — used in tests."""
    global _instance
    _instance = None
