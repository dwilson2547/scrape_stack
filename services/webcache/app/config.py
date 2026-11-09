from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings


class StorageBackend(str, Enum):
    local = "local"
    s3 = "s3"


class Settings(BaseSettings):
    storage_backend: StorageBackend = StorageBackend.local

    # Local storage
    local_storage_path: Path = Path("/data/cache")

    # Database
    database_url: str = "sqlite:////data/webcache.db"

    # S3 / MinIO (only used when storage_backend = s3)
    s3_bucket: str = "webcache"
    s3_endpoint_url: str | None = None  # None → AWS; set to MinIO URL for self-hosted
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_region: str = "us-east-1"

    # Browserless (used by /render endpoint)
    browserless_url: str = "http://browserless:3000"
    browserless_token: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
