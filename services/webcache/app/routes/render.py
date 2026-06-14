import blake3
import time
from datetime import datetime, timedelta, UTC

import lz4.frame
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import metrics
from ..browserless import get_browserless
from ..database import get_db
from ..models import CacheEntry, RenderMetadata
from ..schemas import RenderMetadataCreate, RenderMetadataResponse, RenderResponse
from ..storage import get_storage

router = APIRouter(prefix="/render", tags=["render"])


def _compute_hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


@router.get("", response_model=RenderResponse)
def render_page(
    url: str,
    bucket: str = "default",
    max_age: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Return a browser-rendered page with cookies and request metadata.
    Checks the cache first; calls browserless if no entry exists or max_age is exceeded.
    A new cache version is created only when page content changes.
    Cookies and metadata are always refreshed on a live render.
    """
    meta = db.query(RenderMetadata).filter(
        RenderMetadata.url == url,
        RenderMetadata.bucket == bucket,
    ).first()

    is_fresh = meta is not None and (
        max_age is None
        or (datetime.utcnow() - meta.updated_at).total_seconds() <= max_age
    )

    if is_fresh:
        entry = (
            db.query(CacheEntry)
            .filter(CacheEntry.url == url, CacheEntry.bucket == bucket)
            .order_by(CacheEntry.created_at.desc())
            .first()
        )
        if entry:
            try:
                compressed = get_storage().read(entry.bucket, entry.content_hash)
                content = lz4.frame.decompress(compressed).decode()
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Cache file not found")
            metrics.render_total.add(1, {"result": "hit"})
            return RenderResponse(
                **{
                    "url": entry.url,
                    "bucket": entry.bucket,
                    "content_hash": entry.content_hash,
                    "client_name": entry.client_name,
                    "created_at": entry.created_at,
                    "content": content,
                    "cookies": meta.cookies,
                    "response_metadata": meta.response_metadata,
                    "render_updated_at": meta.updated_at,
                }
            )

    # Cache miss or stale — call browserless
    start = time.perf_counter()
    try:
        result = get_browserless().render(url)
    except Exception as exc:
        metrics.render_total.add(1, {"result": "error"})
        raise HTTPException(status_code=502, detail=f"Browserless error: {exc}") from exc
    finally:
        metrics.render_duration.record(time.perf_counter() - start)

    content_hash = _compute_hash(result.html)
    now = datetime.now(UTC)

    latest_entry = (
        db.query(CacheEntry)
        .filter(CacheEntry.url == url, CacheEntry.bucket == bucket)
        .order_by(CacheEntry.created_at.desc())
        .first()
    )

    if latest_entry is None or latest_entry.content_hash != content_hash:
        compressed = lz4.frame.compress(result.html.encode())
        metrics.compressed_bytes.record(len(compressed))
        storage = get_storage()
        if not storage.exists(bucket, content_hash):
            storage.write(bucket, content_hash, compressed)
        entry = CacheEntry(
            url=url,
            bucket=bucket,
            content_hash=content_hash,
            client_name="browserless",
            created_at=now,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
    else:
        entry = latest_entry

    if meta is None:
        meta = RenderMetadata(
            url=url,
            bucket=bucket,
            cookies=result.cookies,
            response_metadata=result.response_metadata,
            updated_at=now,
        )
        db.add(meta)
    else:
        meta.cookies = result.cookies
        meta.response_metadata = result.response_metadata
        meta.updated_at = now
    db.commit()
    db.refresh(meta)

    metrics.render_total.add(1, {"result": "miss"})
    return RenderResponse(
        **{
            "url": entry.url,
            "bucket": entry.bucket,
            "content_hash": entry.content_hash,
            "client_name": entry.client_name,
            "created_at": entry.created_at,
            "content": result.html,
            "cookies": meta.cookies,
            "response_metadata": meta.response_metadata,
            "render_updated_at": meta.updated_at,
        }
    )


@router.post("/metadata", response_model=RenderMetadataResponse, status_code=201)
def upsert_render_metadata(body: RenderMetadataCreate, db: Session = Depends(get_db)):
    """
    Store or update cookies and response metadata for a URL+bucket.
    Use this when the client performed the rendering itself.
    """
    meta = db.query(RenderMetadata).filter(
        RenderMetadata.url == body.url,
        RenderMetadata.bucket == body.bucket,
    ).first()

    now = datetime.now(UTC)
    if meta is None:
        meta = RenderMetadata(
            url=body.url,
            bucket=body.bucket,
            cookies=body.cookies,
            response_metadata=body.response_metadata,
            updated_at=now,
        )
        db.add(meta)
    else:
        meta.cookies = body.cookies
        meta.response_metadata = body.response_metadata
        meta.updated_at = now

    db.commit()
    db.refresh(meta)
    return meta
