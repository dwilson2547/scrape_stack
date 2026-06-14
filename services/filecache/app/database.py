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
    if "files" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("files")}
        if "client_name" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE files ADD COLUMN client_name VARCHAR"))
            log.info("Migration complete: added files.client_name")


def get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
