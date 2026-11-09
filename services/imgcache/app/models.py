from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
import datetime


class Base(DeclarativeBase):
    pass


class ImageEntry(Base):
    __tablename__ = "image_entries"
    __table_args__ = (UniqueConstraint("bucket", "hash"),)

    id = Column(Integer, primary_key=True, index=True)
    bucket = Column(String, nullable=False, default="")
    prefix = Column(String, nullable=True)
    url = Column(String, index=True)
    hash = Column(String(64), index=True)
    mime_type = Column(String)
    size_bytes = Column(Integer)
    filename = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    perceptual_hash = Column(String(16), nullable=True)
    file_extension = Column(String(10), nullable=True)
    client_name = Column(String)
    created_at = Column(DateTime(timezone=True))
    retrieved_at = Column(DateTime(timezone=True), nullable=True)
    meta_json = Column(Text, nullable=True)
