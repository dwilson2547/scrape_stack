"""Unit tests for the url_map upsert logic and versioning behaviour."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dedup import _upsert_url
from app.models import UrlMap, Video


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _add_video(db, hash: str) -> Video:
    now = _utcnow()
    v = Video(hash=hash, file_path=f"/tmp/{hash}.mp4", bucket="test",
              prefix="", created_at=now, retrieved_at=now)
    db.add(v)
    db.commit()
    return v


# ---------------------------------------------------------------------- #
# Basic upsert                                                             #
# ---------------------------------------------------------------------- #

def test_upsert_url_inserts_new_row(db):
    _add_video(db, "a" * 64)
    _upsert_url(db, "https://example.com/v.mp4", "a" * 64)
    db.commit()
    assert db.query(UrlMap).count() == 1


def test_upsert_url_get_url_roundtrip(db):
    _add_video(db, "a" * 64)
    _upsert_url(db, "https://example.com/v.mp4", "a" * 64)
    db.commit()
    latest = db.query(UrlMap).filter(UrlMap.url == "https://example.com/v.mp4").order_by(UrlMap.id.desc()).first()
    assert latest.hash == "a" * 64


# ---------------------------------------------------------------------- #
# Versioning: same URL + new hash → new row                               #
# ---------------------------------------------------------------------- #

def test_new_hash_for_same_url_creates_new_version(db):
    h1, h2 = "a" * 64, "b" * 64
    _add_video(db, h1)
    _add_video(db, h2)

    url = "https://example.com/v.mp4"
    _upsert_url(db, url, h1)
    db.commit()

    _upsert_url(db, url, h2)
    db.commit()

    latest = db.query(UrlMap).filter(UrlMap.url == url).order_by(UrlMap.id.desc()).first()
    assert latest.hash == h2

    # Both rows exist in history
    all_rows = db.query(UrlMap).filter(UrlMap.url == url).all()
    assert len(all_rows) == 2


# ---------------------------------------------------------------------- #
# Idempotency: same URL + same hash → update seen_at, no new row          #
# ---------------------------------------------------------------------- #

def test_same_url_same_hash_is_idempotent(db):
    h = "c" * 64
    _add_video(db, h)
    url = "https://example.com/v.mp4"

    _upsert_url(db, url, h)
    db.commit()
    _upsert_url(db, url, h)
    db.commit()
    _upsert_url(db, url, h)
    db.commit()

    assert db.query(UrlMap).filter(UrlMap.url == url).count() == 1


# ---------------------------------------------------------------------- #
# Multiple aliases for the same hash                                       #
# ---------------------------------------------------------------------- #

def test_different_urls_same_hash_creates_separate_rows(db):
    h = "d" * 64
    _add_video(db, h)

    _upsert_url(db, "https://cdn.example.com/v.mp4", h)
    _upsert_url(db, "https://mirror.example.com/v.mp4", h)
    db.commit()

    aliases = [u.url for u in db.query(UrlMap).filter(UrlMap.hash == h).all()]
    assert "https://cdn.example.com/v.mp4" in aliases
    assert "https://mirror.example.com/v.mp4" in aliases
