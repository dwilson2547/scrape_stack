from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import metrics, request_auth, storage
from .config import Config
from .database import Base, get_db, get_engine, run_migrations
from .ingest import IngestResult, run_ingest
from .models import File, UrlMap


# ---------------------------------------------------------------------- #
# Request models                                                           #
# ---------------------------------------------------------------------- #

class UploadInitRequest(BaseModel):
    url: str
    bucket: str
    prefix: str | None = None
    filename: str
    content_hash: str | None = None
    meta: dict[str, Any] | None = None
    client_name: str | None = None


class DownloadRequest(BaseModel):
    url: str
    bucket: str
    prefix: str | None = None
    filename: str
    cookies: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    meta: dict[str, Any] | None = None
    client_name: str | None = None


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #

def _latest_url_entry(db: Session, url: str):
    return (
        db.query(UrlMap)
        .filter(UrlMap.url == url)
        .order_by(UrlMap.seen_at.desc())
        .first()
    )


def _file_to_dict(file: File, db: Session) -> dict:
    aliases = list({u.url for u in db.query(UrlMap).filter(UrlMap.hash == file.hash).all()})
    meta = None
    if file.meta_json:
        try:
            meta = json.loads(file.meta_json)
        except json.JSONDecodeError:
            pass
    return {
        "hash": file.hash,
        "file_path": file.file_path,
        "bucket": file.bucket,
        "prefix": file.prefix,
        "size_bytes": file.size_bytes,
        "mime_type": file.mime_type,
        "filename": file.filename,
        "created_at": file.created_at,
        "retrieved_at": file.retrieved_at,
        "meta": meta,
        "aliases": aliases,
        "client_name": file.client_name,
    }


def _parse_range(header: str, total: int) -> "tuple[int, int] | None":
    if not header or not header.startswith("bytes="):
        return None
    try:
        spec = header[6:]
        start_str, end_str = spec.split("-", 1)
        if not start_str and not end_str:
            return None
        if not start_str:
            # Suffix range: bytes=-N means the last N bytes
            n = int(end_str)
            start = max(0, total - n)
            end = total - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else max(0, total - 1)
            end = min(end, total - 1)
        if start > end:
            return None
        return start, end
    except (ValueError, AttributeError):
        return None


async def _iter_store(
    store,
    bucket: str,
    prefix: "str | None",
    content_hash: str,
    ext: str,
    byte_range: "tuple[int, int] | None",
):
    f = await asyncio.to_thread(store.read, bucket, prefix, content_hash, ext, byte_range)
    try:
        while True:
            chunk = await asyncio.to_thread(f.read, 1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(f.close)


# ---------------------------------------------------------------------- #
# Application factory                                                      #
# ---------------------------------------------------------------------- #

def create_app(config: Config) -> FastAPI:
    _upload_sessions: dict[str, dict[str, Any]] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        import os
        engine = get_engine(
            config.index.database_url or f"sqlite:///{config.index.db_path}"
        )
        run_migrations(engine)
        Base.metadata.create_all(bind=engine)
        storage.init_storage(config)
        metrics.init_metrics(
            service_name=os.environ.get("OTEL_SERVICE_NAME", "filecache"),
            otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
        )
        if config.request_auth.enabled:
            request_auth.init_client(config.request_auth.address)
        yield
        metrics.shutdown_metrics()
        if (c := request_auth.get_client()):
            try:
                c.close()
            except Exception:
                pass
        storage.reset_storage()

    app = FastAPI(title="filecache", version="1.0.0", lifespan=lifespan)

    # ------------------------------------------------------------------ #
    # Browse endpoints                                                     #
    # ------------------------------------------------------------------ #

    from .browse import create_browse_router
    app.include_router(create_browse_router())

    # ------------------------------------------------------------------ #
    # Health + metrics                                                     #
    # ------------------------------------------------------------------ #

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def prometheus_metrics():
        return Response(
            content=metrics.get_metrics_output(),
            media_type="text/plain; version=0.0.4",
        )

    # ------------------------------------------------------------------ #
    # POST /upload/init                                                    #
    # ------------------------------------------------------------------ #

    @app.post("/upload/init")
    async def upload_init(body: UploadInitRequest, db: Session = Depends(get_db)):
        # Fast path: client pre-computed BLAKE3 hash — skip upload if content already stored.
        if body.content_hash:
            file_record = db.get(File, body.content_hash)
            if file_record:
                url_entry = _latest_url_entry(db, body.url)
                if url_entry is None or url_entry.hash != body.content_hash:
                    db.add(UrlMap(url=body.url, hash=body.content_hash, seen_at=datetime.now(timezone.utc)))
                file_record.retrieved_at = datetime.now(timezone.utc)
                db.commit()
                metrics.upload_init_total.add(1, {"result": "fresh"})
                return {"status": "fresh", "hash": file_record.hash, "file_path": file_record.file_path}
            # Hash unknown — fall through to pending

        url_entry = _latest_url_entry(db, body.url)
        if url_entry:
            file_record = db.get(File, url_entry.hash)
            if file_record:
                metrics.upload_init_total.add(1, {"result": "cached"})
                return {"status": "cached", "hash": file_record.hash, "file_path": file_record.file_path}

        upload_id = uuid.uuid4().hex
        _upload_sessions[upload_id] = {
            "url": body.url,
            "bucket": body.bucket,
            "prefix": body.prefix,
            "filename": body.filename,
            "meta": body.meta,
            "client_name": body.client_name,
        }
        metrics.upload_init_total.add(1, {"result": "pending"})
        return {"status": "pending", "upload_id": upload_id}

    # ------------------------------------------------------------------ #
    # POST /upload/{upload_id}                                             #
    # ------------------------------------------------------------------ #

    @app.post("/upload/{upload_id}")
    async def upload_stream(upload_id: str, request: Request, db: Session = Depends(get_db)):
        session = _upload_sessions.pop(upload_id, None)
        if session is None:
            raise HTTPException(status_code=404, detail="Upload session not found or already used")

        temp_dir = Path(config.ingest.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{upload_id}.tmp"

        try:
            with open(temp_path, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        try:
            result: IngestResult = await asyncio.to_thread(
                run_ingest,
                temp_path,
                session["url"],
                session["bucket"],
                session["filename"],
                session["meta"],
                db,
                storage.get_storage(),
                session["prefix"],
                session["client_name"],
            )
        finally:
            temp_path.unlink(missing_ok=True)

        metrics.ingest_total.add(1, {"result": result.status})
        if result.status == "new":
            metrics.file_bytes_histogram.record(result.size_bytes)

        return {"status": result.status, "hash": result.hash, "file_path": result.file_path, "size_bytes": result.size_bytes}

    # ------------------------------------------------------------------ #
    # POST /download  (server-side download — sync, runs in threadpool)   #
    # ------------------------------------------------------------------ #

    @app.post("/download")
    def server_download(body: DownloadRequest, db: Session = Depends(get_db)):
        auth = request_auth.get_client()
        if auth is None:
            raise HTTPException(status_code=503, detail="Server-side download unavailable: request_auth not configured")

        url_entry = _latest_url_entry(db, body.url)
        if url_entry:
            file_record = db.get(File, url_entry.hash)
            if file_record:
                metrics.download_total.add(1, {"result": "cached"})
                return _file_to_dict(file_record, db)

        domain = urlparse(body.url).netloc
        permit = auth.acquire(domain)
        permit_released = False

        temp_dir = Path(config.ingest.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid.uuid4().hex}.tmp"

        http_status = 0
        try:
            chunk_size = config.ingest.chunk_size_mb * 1024 * 1024
            with httpx.Client(follow_redirects=True, timeout=None) as http_client:
                with http_client.stream(
                    "GET",
                    body.url,
                    headers=body.headers or {},
                    cookies=body.cookies or {},
                ) as response:
                    http_status = response.status_code
                    response.raise_for_status()
                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size):
                            f.write(chunk)

            permit.release(http_status)
            permit_released = True

            result: IngestResult = run_ingest(
                temp_path=temp_path,
                url=body.url,
                bucket=body.bucket,
                filename=body.filename,
                meta=body.meta,
                db=db,
                store=storage.get_storage(),
                prefix=body.prefix,
                client_name=body.client_name,
            )

            metrics.download_total.add(1, {"result": result.status})
            if result.status == "new":
                metrics.file_bytes_histogram.record(result.size_bytes)

            file_record = db.get(File, result.hash)
            if file_record is None:
                raise HTTPException(status_code=500, detail="File record missing after ingest")
            return _file_to_dict(file_record, db)

        except httpx.HTTPStatusError as exc:
            if not permit_released:
                permit.release(http_status)
            raise HTTPException(status_code=502, detail=f"Remote server returned {exc.response.status_code}")
        except HTTPException:
            if not permit_released:
                permit.release(http_status or 0)
            raise
        except Exception as exc:
            if not permit_released:
                permit.release(0)
            raise HTTPException(status_code=502, detail=f"Download failed: {exc}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------ #
    # GET /cache/meta/{hash}                                              #
    # ------------------------------------------------------------------ #

    @app.get("/cache/meta/{hash}")
    async def get_meta(hash: str, db: Session = Depends(get_db)):
        file_record = db.get(File, hash)
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        return _file_to_dict(file_record, db)

    # ------------------------------------------------------------------ #
    # GET /resolve                                                         #
    # ------------------------------------------------------------------ #

    @app.get("/cache/resolve")
    async def resolve(url: str, db: Session = Depends(get_db)):
        url_entry = _latest_url_entry(db, url)
        if not url_entry:
            raise HTTPException(status_code=404, detail="URL not found")
        return {"hash": url_entry.hash, "url": url}

    # ------------------------------------------------------------------ #
    # GET /lookup                                                          #
    # ------------------------------------------------------------------ #

    @app.get("/cache/lookup")
    async def lookup(
        url: str,
        max_age: int | None = None,
        version: str | None = None,
        db: Session = Depends(get_db),
    ):
        if max_age is not None and version is not None:
            raise HTTPException(status_code=422, detail="max_age and version are mutually exclusive")

        if version is not None:
            file_record = db.get(File, version)
            if not file_record:
                raise HTTPException(status_code=404, detail="Version not found")
            return _file_to_dict(file_record, db)

        url_entry = _latest_url_entry(db, url)
        if not url_entry:
            raise HTTPException(status_code=404, detail="URL not found")

        file_record = db.get(File, url_entry.hash)
        if not file_record:
            raise HTTPException(status_code=404, detail="File record missing")

        if max_age is not None:
            retrieved = file_record.retrieved_at
            if retrieved is not None:
                if retrieved.tzinfo is None:
                    retrieved = retrieved.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - retrieved).total_seconds() > max_age:
                    raise HTTPException(status_code=404, detail="Cache entry exceeds max_age")

        return _file_to_dict(file_record, db)

    # ------------------------------------------------------------------ #
    # GET /search                                                          #
    # ------------------------------------------------------------------ #

    @app.get("/cache/search")
    async def search(url_contains: str, bucket: str = "default", db: Session = Depends(get_db)):
        rows = (
            db.query(UrlMap, File)
            .join(File, UrlMap.hash == File.hash)
            .filter(UrlMap.url.contains(url_contains))
            .filter(File.bucket == bucket)
            .all()
        )
        return [
            {
                "hash": f.hash,
                "url": u.url,
                "filename": f.filename,
                "size_bytes": f.size_bytes,
                "mime_type": f.mime_type,
                "created_at": f.created_at,
                "retrieved_at": f.retrieved_at,
            }
            for u, f in rows
        ]

    # ------------------------------------------------------------------ #
    # GET /cache/{hash}  (streaming download — registered last so         #
    # specific /cache/* paths above take priority)                        #
    # ------------------------------------------------------------------ #

    @app.get("/cache/{hash}")
    async def download_file(hash: str, request: Request, db: Session = Depends(get_db)):
        file_record = db.get(File, hash)
        if not file_record:
            metrics.lookup_total.add(1, {"result": "miss"})
            raise HTTPException(status_code=404, detail="File not found")

        metrics.lookup_total.add(1, {"result": "hit"})

        store = storage.get_storage()
        size = file_record.size_bytes or 0
        ext = Path(file_record.file_path).suffix
        bucket = file_record.bucket
        prefix = file_record.prefix
        media_type = file_record.mime_type or "application/octet-stream"
        filename = file_record.filename or hash

        range_header = request.headers.get("Range")
        byte_range = _parse_range(range_header, size) if range_header and size > 0 else None

        etag = f'"{hash}"'
        if not byte_range and request.headers.get("if-none-match") == etag:
            return Response(status_code=304)

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable",
        }

        if byte_range:
            start, end = byte_range
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            headers["Content-Length"] = str(end - start + 1)
            return StreamingResponse(
                _iter_store(store, bucket, prefix, hash, ext, byte_range),
                status_code=206,
                media_type=media_type,
                headers=headers,
            )

        if size:
            headers["Content-Length"] = str(size)
        return StreamingResponse(
            _iter_store(store, bucket, prefix, hash, ext, None),
            status_code=200,
            media_type=media_type,
            headers=headers,
        )

    # ------------------------------------------------------------------ #
    # DELETE /cache/{hash}                                                 #
    # ------------------------------------------------------------------ #

    @app.delete("/cache/{hash}", status_code=204)
    async def delete_file(hash: str, db: Session = Depends(get_db)):
        file_record = db.get(File, hash)
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        ext = Path(file_record.file_path).suffix
        store = storage.get_storage()
        try:
            await asyncio.to_thread(store.delete, file_record.bucket, file_record.prefix, hash, ext)
        except FileNotFoundError:
            pass
        # Delete url_map aliases explicitly (SQLite ORM cascade requires relationship config)
        db.query(UrlMap).filter(UrlMap.hash == hash).delete(synchronize_session=False)
        db.delete(file_record)
        db.commit()

    return app
