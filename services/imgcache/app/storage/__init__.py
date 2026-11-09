from app.storage.base import BaseStorage

_storage: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage
    if _storage is None:
        raise RuntimeError("Storage not initialised — call init_storage() first")
    return _storage


def init_storage(config) -> None:
    global _storage
    if _storage is not None:
        return  # already set (e.g. via override_storage in tests)
    if config.backend == "s3":
        if config.s3 is None:
            raise ValueError("storage.s3 config required for s3 backend")
        from app.storage.s3 import S3Storage
        s3 = config.s3
        _storage = S3Storage(
            bucket=s3.bucket,
            endpoint_url=s3.endpoint or None,
            aws_access_key_id=s3.access_key or None,
            aws_secret_access_key=s3.secret_key or None,
        )
    else:
        if config.local is None:
            raise ValueError("storage.local config required for local backend")
        from app.storage.local import LocalStorage
        _storage = LocalStorage(config.local.root)


def override_storage(instance: BaseStorage) -> None:
    global _storage
    _storage = instance


def reset_storage() -> None:
    global _storage
    _storage = None
