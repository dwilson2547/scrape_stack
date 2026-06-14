from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class LocalStoreConfig:
    root: str


@dataclass
class S3StoreConfig:
    endpoint: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"


@dataclass
class VideoStoreConfig:
    backend: str = "local"
    local: LocalStoreConfig | None = None
    s3: S3StoreConfig | None = None


@dataclass
class DedupConfig:
    phash_threshold: int = 10
    multipart_threshold_mb: int = 100
    multipart_part_size_mb: int = 64


@dataclass
class IngestConfig:
    chunk_size_mb: int = 1
    temp_dir: str = "/tmp/vidcache"


@dataclass
class IndexConfig:
    db_path: str = "/data/vidcache/index.db"
    database_url: str = ""  # if set, takes priority over db_path


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8020


@dataclass
class RequestAuthConfig:
    enabled: bool = False
    address: str = ""


@dataclass
class Config:
    video_store: VideoStoreConfig = field(default_factory=VideoStoreConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    request_auth: RequestAuthConfig = field(default_factory=RequestAuthConfig)


def load_config(path: str) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    vs_raw = raw.get("video_store", {})
    local_raw = vs_raw.get("local")
    s3_raw = vs_raw.get("s3")

    video_store = VideoStoreConfig(
        backend=vs_raw.get("backend", "local"),
        local=LocalStoreConfig(**local_raw) if local_raw else None,
        s3=S3StoreConfig(**s3_raw) if s3_raw else None,
    )

    dedup_raw = raw.get("dedup", {})
    dedup = DedupConfig(
        phash_threshold=dedup_raw.get("phash_threshold", 10),
        multipart_threshold_mb=dedup_raw.get("multipart_threshold_mb", 100),
        multipart_part_size_mb=dedup_raw.get("multipart_part_size_mb", 64),
    )

    ingest_raw = raw.get("ingest", {})
    ingest = IngestConfig(
        chunk_size_mb=ingest_raw.get("chunk_size_mb", 1),
        temp_dir=ingest_raw.get("temp_dir", "/tmp/vidcache"),
    )

    index_raw = raw.get("index", {})
    index = IndexConfig(
        db_path=index_raw.get("db_path", "/data/vidcache/index.db"),
        database_url=index_raw.get("database_url", ""),
    )

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "0.0.0.0"),
        port=server_raw.get("port", 8020),
    )

    ra_raw = raw.get("request_auth", {})
    request_auth = RequestAuthConfig(
        enabled=ra_raw.get("enabled", False),
        address=ra_raw.get("address", ""),
    )

    if env_db_url := os.environ.get("DATABASE_URL"):
        index = IndexConfig(
            db_path=index_raw.get("db_path", "/data/vidcache/index.db"),
            database_url=env_db_url,
        )

    return Config(
        video_store=video_store,
        dedup=dedup,
        ingest=ingest,
        index=index,
        server=server,
        request_auth=request_auth,
    )
