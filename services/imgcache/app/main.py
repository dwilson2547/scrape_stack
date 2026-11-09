from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import Response
from app.config import settings, load_storage_config
from app.database import get_engine
from app.models import Base
from app import metrics as m
from app.storage import init_storage, reset_storage

_MIGRATIONS = [
    # Column renames (introduced during cache standardisation)
    "ALTER TABLE image_entries RENAME COLUMN content_hash TO hash",
    "ALTER TABLE image_entries RENAME COLUMN content_type TO mime_type",
    "ALTER TABLE image_entries RENAME COLUMN file_size_bytes TO size_bytes",
    "ALTER TABLE image_entries RENAME COLUMN original_filename TO filename",
    # New columns
    "ALTER TABLE image_entries ADD COLUMN prefix VARCHAR NOT NULL DEFAULT ''",
    "ALTER TABLE image_entries ADD COLUMN retrieved_at DATETIME",
    "ALTER TABLE image_entries ADD COLUMN meta_json TEXT",
    # Existing inline migrations kept here for completeness
    "ALTER TABLE image_entries ADD COLUMN file_extension VARCHAR(10)",
    "ALTER TABLE image_entries ADD COLUMN bucket VARCHAR NOT NULL DEFAULT ''",
    # Timestamp standardisation: lookup_time removed (redundant with created_at)
    "ALTER TABLE image_entries DROP COLUMN lookup_time",
]


def _prefix_is_not_null(engine) -> bool:
    """Return True if image_entries.prefix still has a NOT NULL constraint."""
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(text("PRAGMA table_info(image_entries)")).fetchall()
            for row in rows:
                # (cid, name, type, notnull, dflt_value, pk)
                if row[1] == "prefix" and row[3] == 1:
                    return True
        return False
    else:
        from sqlalchemy import inspect as sa_inspect
        for col in sa_inspect(engine).get_columns("image_entries"):
            if col["name"] == "prefix":
                return not col.get("nullable", True)
        return False


def _migrate_prefix_nullable(engine) -> None:
    """Make image_entries.prefix nullable (was NOT NULL DEFAULT '')."""
    if not _prefix_is_not_null(engine):
        return
    from sqlalchemy import text
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE image_entries_new (
                    id               INTEGER NOT NULL PRIMARY KEY,
                    bucket           VARCHAR NOT NULL DEFAULT '',
                    prefix           VARCHAR,
                    url              VARCHAR,
                    hash             VARCHAR(64),
                    mime_type        VARCHAR,
                    size_bytes       INTEGER,
                    filename         VARCHAR,
                    width            INTEGER,
                    height           INTEGER,
                    perceptual_hash  VARCHAR(16),
                    file_extension   VARCHAR(10),
                    client_name      VARCHAR,
                    created_at       DATETIME,
                    retrieved_at     DATETIME,
                    meta_json        TEXT,
                    UNIQUE (bucket, hash)
                )
            """))
            conn.execute(text("""
                INSERT INTO image_entries_new
                SELECT id, bucket, NULLIF(prefix, ''), url, hash, mime_type,
                       size_bytes, filename, width, height, perceptual_hash,
                       file_extension, client_name, created_at, retrieved_at, meta_json
                FROM image_entries
            """))
            conn.execute(text("DROP TABLE image_entries"))
            conn.execute(text("ALTER TABLE image_entries_new RENAME TO image_entries"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_image_entries_url ON image_entries (url)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_image_entries_hash ON image_entries (hash)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_image_entries_id ON image_entries (id)"))
    else:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE image_entries ALTER COLUMN prefix DROP NOT NULL"))
            conn.execute(text("UPDATE image_entries SET prefix = NULL WHERE prefix = ''"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        from sqlalchemy import text
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()  # Postgres requires rollback after a failed statement
        conn.execute(text("UPDATE image_entries SET bucket = '' WHERE bucket IS NULL"))
        conn.commit()
    _migrate_prefix_nullable(engine)
    m.init_metrics(settings.otel_service_name, settings.otel_exporter_otlp_endpoint)
    storage_cfg = load_storage_config(settings.config_path)
    init_storage(storage_cfg)
    yield
    m.shutdown_metrics()
    reset_storage()


app = FastAPI(title="imgcache", lifespan=lifespan)

from app.routes.cache import router
from app.routes.browse import router as browse_router
app.include_router(router)
app.include_router(browse_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def prometheus_metrics():
    from prometheus_client import CONTENT_TYPE_LATEST
    return Response(m.get_metrics_output(), media_type=CONTENT_TYPE_LATEST)
