from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from .database import Base


class File(Base):
    __tablename__ = "files"

    hash = Column(String(64), primary_key=True)
    file_path = Column(Text, nullable=False)
    bucket = Column(String, nullable=False)
    prefix = Column(String, nullable=True)
    size_bytes = Column(Integer)
    mime_type = Column(String)
    filename = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    meta_json = Column(Text)
    client_name = Column(String, nullable=True)


class UrlMap(Base):
    __tablename__ = "url_map"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False, index=True)
    hash = Column(String(64), ForeignKey("files.hash", ondelete="CASCADE"), nullable=False)
    seen_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_url_hash", "hash"),)
