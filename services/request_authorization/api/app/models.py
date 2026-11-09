from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Bucket(Base):
    __tablename__ = "buckets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    pool_size: Mapped[Optional[int]] = mapped_column(Integer)
    base_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    backoff_multiplier: Mapped[Optional[float]] = mapped_column(Float)
    max_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    recovery_threshold: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    domains: Mapped[list["Domain"]] = relationship("Domain", back_populates="bucket")


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column("name", String, unique=True, nullable=False)
    bucket_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("buckets.id", ondelete="SET NULL"))
    pool_size: Mapped[Optional[int]] = mapped_column(Integer)
    base_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    backoff_multiplier: Mapped[Optional[float]] = mapped_column(Float)
    max_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    recovery_threshold: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    bucket: Mapped[Optional[Bucket]] = relationship("Bucket", back_populates="domains")


class RobotsTxtCache(Base):
    __tablename__ = "robots_txt_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    raw_content: Mapped[Optional[str]] = mapped_column(String)
    crawl_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    original_crawl_delay_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GlobalConfig(Base):
    __tablename__ = "global_config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
