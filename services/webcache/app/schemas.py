from datetime import datetime

from pydantic import BaseModel


class CacheEntryCreate(BaseModel):
    url: str
    content: str
    content_hash: str
    client_name: str
    bucket: str = "default"
    prefix: str | None = None
    cookies: list | None = None
    response_metadata: dict | None = None


class CacheEntryMeta(BaseModel):
    url: str
    bucket: str
    prefix: str | None = None
    content_hash: str
    client_name: str
    created_at: datetime
    retrieved_at: datetime | None = None

    model_config = {"from_attributes": True}


class CacheEntryFull(CacheEntryMeta):
    content: str


class RenderMetadataCreate(BaseModel):
    url: str
    bucket: str = "default"
    cookies: list | None = None
    response_metadata: dict | None = None


class RenderMetadataResponse(BaseModel):
    url: str
    bucket: str
    cookies: list | None
    response_metadata: dict | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class RenderResponse(CacheEntryFull):
    cookies: list | None = None
    response_metadata: dict | None = None
    render_updated_at: datetime | None = None


class BucketConfigUpdate(BaseModel):
    """Limits for a bucket. Both None means unlimited (config disabled)."""
    max_entries: int | None = None
    max_total_bytes: int | None = None


class BucketStats(BaseModel):
    entries: int
    total_bytes: int


class BucketConfigResponse(BaseModel):
    bucket: str
    max_entries: int | None = None
    max_total_bytes: int | None = None
    created_at: datetime
    updated_at: datetime
    stats: BucketStats

    model_config = {"from_attributes": True}
