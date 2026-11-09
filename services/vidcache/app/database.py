from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    global _engine, _SessionLocal
    if _engine is None:
        is_sqlite = database_url.startswith("sqlite")

        if is_sqlite:
            db_path = database_url.split("sqlite:///", 1)[-1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        else:
            connect_args = {}

        _engine = create_engine(database_url, connect_args=connect_args)

        if is_sqlite:
            @event.listens_for(_engine, "connect")
            def _set_pragma(conn, _):
                conn.execute(text("PRAGMA foreign_keys = ON"))

        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def run_migrations(engine) -> None:
    inspector = inspect(engine)
    if "videos" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("videos")}
        if "first_seen" in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE videos RENAME COLUMN first_seen TO created_at"))
            log.info("Migration complete: videos.first_seen → created_at")
        _migrate_prefix_nullable(engine)
        # Re-inspect after potential table rebuild (SQLite caches metadata)
        cols = {c["name"] for c in inspect(engine).get_columns("videos")}
        if "client_name" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE videos ADD COLUMN client_name VARCHAR"))
            log.info("Migration complete: added videos.client_name")


def _prefix_is_not_null(engine, table: str) -> bool:
    """Return True if the prefix column still has a NOT NULL constraint."""
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            for row in rows:
                # (cid, name, type, notnull, dflt_value, pk)
                if row[1] == "prefix" and row[3] == 1:
                    return True
        return False
    else:
        inspector = inspect(engine)
        for col in inspector.get_columns(table):
            if col["name"] == "prefix":
                return not col.get("nullable", True)
        return False


def _migrate_prefix_nullable(engine) -> None:
    """Make videos.prefix nullable (was NOT NULL DEFAULT '')."""
    if not _prefix_is_not_null(engine, "videos"):
        return
    log.info("Migrating videos.prefix → nullable")
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("""
                CREATE TABLE videos_new (
                    hash       VARCHAR(64) NOT NULL PRIMARY KEY,
                    phash      VARCHAR,
                    file_path  TEXT NOT NULL,
                    bucket     VARCHAR NOT NULL,
                    prefix     VARCHAR,
                    size_bytes INTEGER,
                    duration_s FLOAT,
                    mime_type  VARCHAR,
                    filename   VARCHAR,
                    created_at DATETIME NOT NULL,
                    retrieved_at DATETIME NOT NULL,
                    source_url VARCHAR,
                    meta_json  TEXT,
                    client_name VARCHAR
                )
            """))
            conn.execute(text("""
                INSERT INTO videos_new
                SELECT hash, phash, file_path, bucket,
                       NULLIF(prefix, ''),
                       size_bytes, duration_s, mime_type, filename,
                       created_at, retrieved_at, source_url, meta_json,
                       client_name
                FROM videos
            """))
            conn.execute(text("DROP TABLE videos"))
            conn.execute(text("ALTER TABLE videos_new RENAME TO videos"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phash ON videos (phash)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bucket ON videos (bucket, prefix)"))
            conn.execute(text("PRAGMA foreign_keys = ON"))
    else:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE videos ALTER COLUMN prefix DROP NOT NULL"))
            conn.execute(text("UPDATE videos SET prefix = NULL WHERE prefix = ''"))
    log.info("Migration complete: videos.prefix is now nullable")


def get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
