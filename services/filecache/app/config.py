from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class LocalStorageConfig:
    root: str = "/data/filecache"


@dataclass
class S3Config:
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    bucket: str = "filecache"
    multipart_threshold_mb: int = 100
    multipart_part_size_mb: int = 64


@dataclass
class StorageConfig:
    backend: str = "local"
    local: LocalStorageConfig | None = None
    s3: S3Config | None = None


@dataclass
class IndexConfig:
    db_path: str = "/data/filecache/index.db"
    database_url: str = ""  # if set, takes priority over db_path


@dataclass
class RequestAuthConfig:
    address: str = "localhost:9000"
    enabled: bool = True


@dataclass
class IngestConfig:
    temp_dir: str = "/tmp/filecache"
    chunk_size_mb: int = 1


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8030


@dataclass
class Config:
    storage: StorageConfig = field(default_factory=StorageConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    request_auth: RequestAuthConfig = field(default_factory=RequestAuthConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def load_config(path: str) -> Config:
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    cfg = Config()

    if s := data.get("storage"):
        backend = s.get("backend", "local")
        local_cfg = None
        s3_cfg = None
        if loc := s.get("local"):
            local_cfg = LocalStorageConfig(root=loc.get("root", "/data/filecache"))
        if s3 := s.get("s3"):
            s3_cfg = S3Config(
                endpoint=s3.get("endpoint", ""),
                access_key=s3.get("access_key", ""),
                secret_key=s3.get("secret_key", ""),
                region=s3.get("region", "us-east-1"),
                bucket=s3.get("bucket", "filecache"),
                multipart_threshold_mb=s3.get("multipart_threshold_mb", 100),
                multipart_part_size_mb=s3.get("multipart_part_size_mb", 64),
            )
        cfg.storage = StorageConfig(backend=backend, local=local_cfg, s3=s3_cfg)

    if idx := data.get("index"):
        cfg.index = IndexConfig(
            db_path=idx.get("db_path", "/data/filecache/index.db"),
            database_url=idx.get("database_url", ""),
        )

    if ra := data.get("request_auth"):
        cfg.request_auth = RequestAuthConfig(
            address=ra.get("address", "localhost:9000"),
            enabled=ra.get("enabled", True),
        )

    if ing := data.get("ingest"):
        cfg.ingest = IngestConfig(
            temp_dir=ing.get("temp_dir", "/tmp/filecache"),
            chunk_size_mb=ing.get("chunk_size_mb", 1),
        )

    if srv := data.get("server"):
        cfg.server = ServerConfig(
            host=srv.get("host", "0.0.0.0"),
            port=srv.get("port", 8030),
        )

    if env_db_url := os.environ.get("DATABASE_URL"):
        cfg.index.database_url = env_db_url

    return cfg
