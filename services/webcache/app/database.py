import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def run_migrations(engine) -> None:
    """Apply any pending schema migrations at startup. Idempotent."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "cache_entries" in existing_tables:
        cols = {c["name"] for c in inspector.get_columns("cache_entries")}
        if "bucket" not in cols:
            log.info("Migrating cache_entries: adding bucket column and removing unique constraint on content_hash")
            _migrate_add_bucket(engine)
        if "retrieved_at" not in cols:
            log.info("Migrating cache_entries: adding retrieved_at column")
            _migrate_add_column(engine, "cache_entries", "retrieved_at", "DATETIME")
        if "prefix" not in cols:
            log.info("Migrating cache_entries: adding prefix column")
            _migrate_add_column(engine, "cache_entries", "prefix", "VARCHAR")
        if "lookup_time" in cols:
            log.info("Migrating cache_entries: dropping lookup_time column")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cache_entries DROP COLUMN lookup_time"))

    # render_metadata and any other new tables are handled by create_all() after this call.


_engine = None
_SessionLocal = None


def _migrate_add_column(engine, table: str, column: str, col_type: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    log.info("Migration complete: %s.%s", table, column)


def _migrate_add_bucket(engine) -> None:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(text("""
                CREATE TABLE cache_entries_new (
                    id           INTEGER NOT NULL PRIMARY KEY,
                    url          VARCHAR NOT NULL,
                    bucket       VARCHAR NOT NULL DEFAULT 'default',
                    content_hash VARCHAR(64) NOT NULL,
                    client_name  VARCHAR NOT NULL,
                    lookup_time  DATETIME NOT NULL,
                    created_at   DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                INSERT INTO cache_entries_new (id, url, bucket, content_hash, client_name, lookup_time, created_at)
                SELECT id, url, 'default', content_hash, client_name, lookup_time, created_at
                FROM cache_entries
            """))
            conn.execute(text("DROP TABLE cache_entries"))
            conn.execute(text("ALTER TABLE cache_entries_new RENAME TO cache_entries"))
        else:
            # PostgreSQL / MySQL support ALTER TABLE directly
            conn.execute(text("ALTER TABLE cache_entries ADD COLUMN bucket VARCHAR NOT NULL DEFAULT 'default'"))
            conn.execute(text("ALTER TABLE cache_entries DROP CONSTRAINT IF EXISTS cache_entries_content_hash_key"))
            conn.execute(text("DROP INDEX IF EXISTS ix_cache_entries_url"))

        conn.execute(text(
            "CREATE INDEX ix_cache_entries_bucket_url_created ON cache_entries (bucket, url, created_at)"
        ))
    log.info("Migration complete")


def get_engine():
    global _engine
    if _engine is None:
        from .config import settings

        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
