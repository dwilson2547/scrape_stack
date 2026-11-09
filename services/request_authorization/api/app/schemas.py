from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ------------------------------------------------------------------
# Bucket
# ------------------------------------------------------------------

class BucketBase(BaseModel):
    name: str
    pool_size: Optional[int] = None
    base_delay_ms: Optional[int] = None
    backoff_multiplier: Optional[float] = None
    max_delay_ms: Optional[int] = None
    recovery_threshold: Optional[int] = None


class BucketCreate(BucketBase):
    pass


class BucketUpdate(BaseModel):
    name: Optional[str] = None
    pool_size: Optional[int] = None
    base_delay_ms: Optional[int] = None
    backoff_multiplier: Optional[float] = None
    max_delay_ms: Optional[int] = None
    recovery_threshold: Optional[int] = None


class BucketRead(BucketBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BucketDetail(BucketRead):
    domains: list["DomainRead"] = []


# ------------------------------------------------------------------
# Domain
# ------------------------------------------------------------------

class DomainBase(BaseModel):
    hostname: str
    bucket_id: Optional[int] = None
    pool_size: Optional[int] = None
    base_delay_ms: Optional[int] = None
    backoff_multiplier: Optional[float] = None
    max_delay_ms: Optional[int] = None
    recovery_threshold: Optional[int] = None


class DomainCreate(DomainBase):
    pass


class DomainUpdate(BaseModel):
    bucket_id: Optional[int] = None
    pool_size: Optional[int] = None
    base_delay_ms: Optional[int] = None
    backoff_multiplier: Optional[float] = None
    max_delay_ms: Optional[int] = None
    recovery_threshold: Optional[int] = None


class DomainRead(DomainBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# robots.txt
# ------------------------------------------------------------------

class RobotsRead(BaseModel):
    domain: str
    crawl_delay_ms: Optional[int]
    fetched_at: Optional[datetime]
    expires_at: Optional[datetime]
    checked_at: Optional[datetime]
    is_overridden: bool
    override_delay_ms: Optional[int]
    original_crawl_delay_ms: Optional[int]

    model_config = {"from_attributes": True}


class RobotsOverrideRequest(BaseModel):
    override_delay_ms: int


# ------------------------------------------------------------------
# Global config
# ------------------------------------------------------------------

class ConfigRead(BaseModel):
    default_pool_size: int
    default_base_delay_ms: int
    default_backoff_multiplier: float
    default_max_delay_ms: int
    default_recovery_threshold: int
    robots_txt_ttl_hours: int
    robots_txt_retry_hours: int
    config_reload_interval_seconds: int


class ConfigUpdate(BaseModel):
    default_pool_size: Optional[int] = None
    default_base_delay_ms: Optional[int] = None
    default_backoff_multiplier: Optional[float] = None
    default_max_delay_ms: Optional[int] = None
    default_recovery_threshold: Optional[int] = None
    robots_txt_ttl_hours: Optional[int] = None
    robots_txt_retry_hours: Optional[int] = None
    config_reload_interval_seconds: Optional[int] = None


# ------------------------------------------------------------------
# Bucket domain membership
# ------------------------------------------------------------------

class BucketDomainAdd(BaseModel):
    domain_id: int


BucketDetail.model_rebuild()
