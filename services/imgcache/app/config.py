from __future__ import annotations

from dataclasses import dataclass

import yaml
from pydantic_settings import BaseSettings


@dataclass
class LocalStorageConfig:
    root: str = "./data"


@dataclass
class S3Config:
    bucket: str = "imgcache"
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"


@dataclass
class StorageConfig:
    backend: str = "local"
    local: LocalStorageConfig | None = None
    s3: S3Config | None = None


def load_storage_config(path: str) -> StorageConfig:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return StorageConfig(backend="local", local=LocalStorageConfig())

    s = data.get("storage", {})
    backend = s.get("backend", "local")

    local_cfg: LocalStorageConfig | None = None
    if loc := s.get("local"):
        local_cfg = LocalStorageConfig(root=loc.get("root", "./data"))
    else:
        local_cfg = LocalStorageConfig()

    s3_cfg: S3Config | None = None
    if s3 := s.get("s3"):
        s3_cfg = S3Config(
            bucket=s3.get("bucket", "imgcache"),
            endpoint=s3.get("endpoint", ""),
            access_key=s3.get("access_key", ""),
            secret_key=s3.get("secret_key", ""),
            region=s3.get("region", "us-east-1"),
        )

    return StorageConfig(backend=backend, local=local_cfg, s3=s3_cfg)


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/imgcache.db"
    config_path: str = "/etc/imgcache/config.yaml"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "imgcache"

    class Config:
        env_file = ".env"


settings = Settings()
