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

from . import metrics, request_auth
from . import storage as storage_module
from .browse import create_browse_router
from .config import Config
from .database import Base, get_db, get_engine, run_migrations
from .dedup import IngestResult, run_pipeline
from .models import UrlMap, Video


# ---------------------------------------------------------------------- #
# Request models                                                           #
# ---------------------------------------------------------------------- #

class UploadInitRequest(BaseModel):
    url: str
    bucket: str
    prefix: str | None = None
    filename: str | None = None
    meta: dict[str, Any] | None = None
    client_name: str | None = None


class DownloadRequest(BaseModel):
    url: str
    bucket: str
    prefix: str | None = None
    filename: str | None = None
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
        .order_by(UrlMap.id.desc())
        .first()
    )


def _video_to_dict(video: Video, db: Session) -> dict[str, Any]:
    aliases = [u.url for u in db.query(UrlMap).filter(UrlMap.hash == video.hash).all()]
    meta = None
    if video.meta_json:
        try:
            meta = json.loads(video.meta_json)
        except json.JSONDecodeError:
            pass
    return {
        "hash": video.hash,
        "phash": video.phash,
        "file_path": video.file_path,
        "bucket": video.bucket,
        "prefix": video.prefix,
        "size_bytes": video.size_bytes,
        "duration_s": video.duration_s,
        "mime_type": video.mime_type,
        "filename": video.filename,
        "created_at": video.created_at,
        "retrieved_at": video.retrieved_at,
        "source_url": video.source_url,
        "meta": meta,
        "aliases": aliases,
        "client_name": video.client_name,
    }


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    if not header or not header.startswith("bytes="):
        return None
    try:
        spec = header[6:]
        start_str, end_str = spec.split("-", 1)
        if not start_str and not end_str:
            return None
        if not start_str:
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


async def _iter_store(store, bucket, prefix, content_hash, byte_range, ext=".mp4"):
    f = await asyncio.to_thread(store.get, bucket, prefix or "", content_hash, byte_range, ext)
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
        storage_module.init_storage(config)
        metrics.setup_metrics(service_name=os.environ.get("OTEL_SERVICE_NAME", "vidcache"))
        if config.request_auth.enabled:
            request_auth.init_client(config.request_auth.address)
        yield
        storage_module.reset_storage()
        if (c := request_auth.get_client()):
            try:
                c.close()
            except Exception:
                pass
        request_auth.reset_client()

    app = FastAPI(title="vidcache", version="1.0.0", lifespan=lifespan)

    app.include_router(create_browse_router())

    # ------------------------------------------------------------------ #
    # Health + metrics                                                     #
    # ------------------------------------------------------------------ #

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def prometheus_metrics():
        return Response(content="# vidcache metrics\n", media_type="text/plain; version=0.0.4")

    # ------------------------------------------------------------------ #
    # POST /upload/init                                                    #
    # ------------------------------------------------------------------ #

    @app.post("/upload/init")
    async def upload_init(body: UploadInitRequest, db: Session = Depends(get_db)):
        url_entry = _latest_url_entry(db, body.url)
        if url_entry:
            video = db.get(Video, url_entry.hash)
            if video:
                video.retrieved_at = datetime.now(timezone.utc)
                db.commit()
                metrics.upload_init_total.add(1, {"result": "cached"})
                return {
                    "status": "cached",
                    "hash": video.hash,
                    "file_path": video.file_path,
                }

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
                run_pipeline,
                temp_path,
                session["url"],
                session["bucket"],
                session["prefix"],
                session["meta"],
                config,
                db,
                storage_module.get_storage(),
                session["filename"],
                session["client_name"],
            )
        finally:
            temp_path.unlink(missing_ok=True)

        metrics.ingest_total.add(1, {"result": result.status})
        resp: dict[str, Any] = {
            "hash": result.hash,
            "status": result.status,
            "file_path": result.file_path,
            "size_bytes": result.size_bytes,
        }
        if result.phash_distance is not None:
            resp["phash_distance"] = result.phash_distance
        return resp

    # ------------------------------------------------------------------ #
    # POST /download  (server-side download — sync, runs in threadpool)   #
    # ------------------------------------------------------------------ #

    @app.post("/download")
    def server_download(body: DownloadRequest, db: Session = Depends(get_db)):
        auth = request_auth.get_client()
        if auth is None:
            raise HTTPException(
                status_code=503,
                detail="Server-side download unavailable: request_auth not configured",
            )

        url_entry = _latest_url_entry(db, body.url)
        if url_entry:
            video = db.get(Video, url_entry.hash)
            if video:
                video.retrieved_at = datetime.now(timezone.utc)
                db.commit()
                metrics.ingest_total.add(1, {"result": "cached"})
                return _video_to_dict(video, db)

        domain = urlparse(body.url).netloc
        permit = auth.acquire(domain)
        permit_released = False

        temp_dir = Path(config.ingest.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid.uuid4().hex}.tmp"

        http_status = 0
        try:
            chunk_size = config.ingest.chunk_size_mb * 1024 * 1024
            with httpx.Client(follow_redirects=True, timeout=None) as client:
                with client.stream(
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

            result: IngestResult = run_pipeline(
                temp_path=temp_path,
                url=body.url,
                bucket=body.bucket,
                prefix=body.prefix,
                meta=body.meta,
                config=config,
                db=db,
                store=storage_module.get_storage(),
                filename=body.filename,
                client_name=body.client_name,
            )

            metrics.ingest_total.add(1, {"result": result.status})
            video = db.get(Video, result.hash)
            if video is None:
                raise HTTPException(status_code=500, detail="Video record missing after ingest")
            return _video_to_dict(video, db)

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
    # NOTE: specific /cache/* paths must be registered before /cache/{hash}
    # so FastAPI doesn't swallow them as the hash parameter.
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # GET /cache/meta/{hash}                                               #
    # ------------------------------------------------------------------ #

    @app.get("/cache/meta/{hash}")
    async def get_meta(hash: str, db: Session = Depends(get_db)):
        video = db.get(Video, hash)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        return _video_to_dict(video, db)

    # ------------------------------------------------------------------ #
    # GET /cache/resolve                                                   #
    # ------------------------------------------------------------------ #

    @app.get("/cache/resolve")
    async def resolve(url: str, db: Session = Depends(get_db)):
        url_entry = _latest_url_entry(db, url)
        if not url_entry:
            raise HTTPException(status_code=404, detail="URL not found")
        return {"hash": url_entry.hash, "url": url}

    # ------------------------------------------------------------------ #
    # GET /cache/lookup                                                    #
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
            video = db.get(Video, version)
            if not video:
                raise HTTPException(status_code=404, detail="Version not found")
            return _video_to_dict(video, db)

        url_entry = _latest_url_entry(db, url)
        if not url_entry:
            raise HTTPException(status_code=404, detail="URL not found")

        video = db.get(Video, url_entry.hash)
        if not video:
            raise HTTPException(status_code=404, detail="Video record missing")

        if max_age is not None:
            ts = video.retrieved_at or video.created_at
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - ts).total_seconds() > max_age:
                    raise HTTPException(status_code=404, detail="Cache entry exceeds max_age")

        return _video_to_dict(video, db)

    # ------------------------------------------------------------------ #
    # GET /cache/search                                                    #
    # ------------------------------------------------------------------ #

    @app.get("/cache/search")
    async def search(url_contains: str, bucket: str = "default", db: Session = Depends(get_db)):
        rows = (
            db.query(UrlMap, Video)
            .join(Video, UrlMap.hash == Video.hash)
            .filter(UrlMap.url.contains(url_contains))
            .filter(Video.bucket == bucket)
            .all()
        )
        return [
            {
                "hash": v.hash,
                "url": u.url,
                "filename": v.filename,
                "size_bytes": v.size_bytes,
                "mime_type": v.mime_type,
                "created_at": v.created_at,
                "retrieved_at": v.retrieved_at,
            }
            for u, v in rows
        ]

    # ------------------------------------------------------------------ #
    # GET /cache/{hash}  (streaming — registered after specific paths)    #
    # ------------------------------------------------------------------ #

    @app.get("/cache/{hash}")
    async def get_video(hash: str, request: Request, db: Session = Depends(get_db)):
        video = db.get(Video, hash)
        if not video:
            metrics.lookup_total.add(1, {"result": "miss"})
            raise HTTPException(status_code=404, detail="Video not found")

        metrics.lookup_total.add(1, {"result": "hit"})
        size: int = video.size_bytes or 0
        range_header = request.headers.get("Range")
        byte_range = _parse_range(range_header, size) if range_header else None
        media_type: str = video.mime_type or "video/mp4"
        ext = Path(video.file_path).suffix or ".mp4"
        filename = video.filename or hash

        etag = f'"{hash}"'
        if not byte_range and request.headers.get("if-none-match") == etag:
            return Response(status_code=304)

        headers: dict[str, str] = {
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
                _iter_store(storage_module.get_storage(), video.bucket,
                            video.prefix, hash, byte_range, ext),
                status_code=206,
                media_type=media_type,
                headers=headers,
            )

        if size:
            headers["Content-Length"] = str(size)
        return StreamingResponse(
            _iter_store(storage_module.get_storage(), video.bucket,
                        video.prefix, hash, None, ext),
            status_code=200,
            media_type=media_type,
            headers=headers,
        )

    # ------------------------------------------------------------------ #
    # DELETE /cache/{hash}                                                 #
    # ------------------------------------------------------------------ #

    @app.delete("/cache/{hash}", status_code=204)
    async def delete_video(hash: str, db: Session = Depends(get_db)):
        video = db.get(Video, hash)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        ext = Path(video.file_path).suffix or ".mp4"
        await asyncio.to_thread(
            storage_module.get_storage().delete,
            video.bucket, video.prefix or "", hash, ext,
        )
        db.query(UrlMap).filter(UrlMap.hash == hash).delete(synchronize_session=False)
        db.delete(video)
        db.commit()

    return app
