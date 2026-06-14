import base64
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import Video


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _encode_cursor(ts: datetime, hash_val: str) -> str:
    payload = {"ts": ts.isoformat(), "hash": hash_val}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["ts"])
        h = payload["hash"]
        return ts, h
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid cursor")


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def _video_to_browse_dict(video: Video) -> dict[str, Any]:
    return {
        "hash": video.hash,
        "url": video.source_url,
        "filename": video.filename,
        "bucket": video.bucket,
        "prefix": video.prefix,
        "client_name": video.client_name,
        "mime_type": video.mime_type,
        "size_bytes": video.size_bytes,
        "duration_s": video.duration_s,
        "created_at": video.created_at.isoformat(),
        "retrieved_at": video.retrieved_at.isoformat() if video.retrieved_at else None,
        "cache_type": "video",
    }


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_browse_router() -> APIRouter:
    router = APIRouter(tags=["browse"])

    @router.get("/browse/buckets")
    def list_buckets(db: Session = Depends(get_db)):
        """List all distinct bucket names."""
        rows = db.query(Video.bucket).distinct().order_by(Video.bucket).all()
        return {"buckets": [r[0] for r in rows]}

    @router.get("/browse/prefixes")
    def list_prefixes(
        bucket: str = Query(..., description="Bucket to list prefixes for"),
        db: Session = Depends(get_db),
    ):
        """List all distinct prefixes within a bucket."""
        rows = (
            db.query(Video.prefix)
            .filter(Video.bucket == bucket)
            .distinct()
            .order_by(Video.prefix)
            .all()
        )
        return {"prefixes": [r[0] for r in rows]}

    @router.get("/browse")
    def browse(
        bucket: str | None = None,
        prefix: str | None = None,
        client_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        order: str = Query(default="desc", pattern="^(desc|asc)$"),
        db: Session = Depends(get_db),
    ):
        """
        Paginated list of video records with optional filters and cursor-based pagination.
        """
        query = db.query(Video)

        # --- Static filters ---
        if bucket is not None:
            query = query.filter(Video.bucket == bucket)
        if prefix is not None:
            query = query.filter(Video.prefix == prefix)
        if client_name is not None:
            query = query.filter(Video.client_name == client_name)
        if date_from is not None:
            query = query.filter(Video.created_at >= date_from)
        if date_to is not None:
            query = query.filter(Video.created_at <= date_to)
        if q is not None:
            query = query.filter(Video.source_url.ilike(f"%{q}%"))

        # --- Cursor / keyset pagination ---
        if cursor is not None:
            cursor_ts, cursor_hash = _decode_cursor(cursor)
            if order == "desc":
                query = query.filter(
                    or_(
                        Video.created_at < cursor_ts,
                        and_(
                            Video.created_at == cursor_ts,
                            Video.hash < cursor_hash,
                        ),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        Video.created_at > cursor_ts,
                        and_(
                            Video.created_at == cursor_ts,
                            Video.hash > cursor_hash,
                        ),
                    )
                )

        # --- Ordering ---
        if order == "desc":
            query = query.order_by(Video.created_at.desc(), Video.hash.desc())
        else:
            query = query.order_by(Video.created_at.asc(), Video.hash.asc())

        # --- Fetch limit+1 to detect next page ---
        rows = query.limit(limit + 1).all()

        has_more = len(rows) > limit
        items = rows[:limit]

        next_cursor = None
        if has_more and items:
            last_video = items[-1]
            next_cursor = _encode_cursor(last_video.created_at, last_video.hash)

        return {
            "items": [_video_to_browse_dict(v) for v in items],
            "next_cursor": next_cursor,
        }

    return router
