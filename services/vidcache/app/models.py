from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from .database import Base


class Video(Base):
    __tablename__ = "videos"

    hash = Column(String(64), primary_key=True)
    phash = Column(String)
    file_path = Column(Text, nullable=False)
    bucket = Column(String, nullable=False)
    prefix = Column(String, nullable=True)
    size_bytes = Column(Integer)
    duration_s = Column(Float)
    mime_type = Column(String)
    filename = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    source_url = Column(String)
    meta_json = Column(Text)
    client_name = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_phash", "phash"),
        Index("idx_bucket", "bucket", "prefix"),
    )


class UrlMap(Base):
    __tablename__ = "url_map"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False, index=True)
    hash = Column(String(64), ForeignKey("videos.hash", ondelete="CASCADE"), nullable=False)
    seen_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_url_hash", "hash"),)
