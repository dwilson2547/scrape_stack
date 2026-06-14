import base64
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import ImageEntry

router = APIRouter(tags=["browse"])


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _encode_cursor(ts: datetime, image_hash: str) -> str:
    payload = {"ts": ts.isoformat(), "hash": image_hash}
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
# Response builders
# ---------------------------------------------------------------------------

def _entry_to_dict(entry: ImageEntry) -> dict[str, Any]:
    return {
        "hash": entry.hash,
        "url": entry.url,
        "bucket": entry.bucket,
        "prefix": entry.prefix,
        "client_name": entry.client_name,
        "mime_type": entry.mime_type,
        "size_bytes": entry.size_bytes,
        "width": entry.width,
        "height": entry.height,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "retrieved_at": entry.retrieved_at.isoformat() if entry.retrieved_at else None,
        "cache_type": "image",  # identifies source service for the cache browser
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/browse/buckets")
def list_buckets(db: Session = Depends(get_session)):
    """List all distinct bucket names."""
    rows = db.query(ImageEntry.bucket).distinct().order_by(ImageEntry.bucket).all()
    return {"buckets": [r[0] for r in rows]}


@router.get("/browse/prefixes")
def list_prefixes(
    bucket: str = Query(..., description="Bucket to list prefixes for"),
    db: Session = Depends(get_session),
):
    """List all distinct prefixes within a bucket."""
    rows = (
        db.query(ImageEntry.prefix)
        .filter(ImageEntry.bucket == bucket)
        .distinct()
        .order_by(ImageEntry.prefix)
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
    db: Session = Depends(get_session),
):
    """
    Paginated list of image cache entries with optional filters and cursor-based pagination.
    """
    query = db.query(ImageEntry)

    # --- Static filters ---
    if bucket is not None:
        query = query.filter(ImageEntry.bucket == bucket)
    if prefix is not None:
        query = query.filter(ImageEntry.prefix == prefix)
    if client_name is not None:
        query = query.filter(ImageEntry.client_name == client_name)
    if date_from is not None:
        query = query.filter(ImageEntry.created_at >= date_from)
    if date_to is not None:
        query = query.filter(ImageEntry.created_at <= date_to)
    if q is not None:
        query = query.filter(ImageEntry.url.ilike(f"%{q}%"))

    # --- Cursor / keyset pagination ---
    # INDEX: (created_at DESC, hash DESC) on image_entries for performance
    if cursor is not None:
        cursor_ts, cursor_hash = _decode_cursor(cursor)
        if order == "desc":
            query = query.filter(
                or_(
                    ImageEntry.created_at < cursor_ts,
                    and_(
                        ImageEntry.created_at == cursor_ts,
                        ImageEntry.hash < cursor_hash,
                    ),
                )
            )
        else:
            query = query.filter(
                or_(
                    ImageEntry.created_at > cursor_ts,
                    and_(
                        ImageEntry.created_at == cursor_ts,
                        ImageEntry.hash > cursor_hash,
                    ),
                )
            )

    # --- Ordering ---
    # Always sort by created_at (cursor pagination is keyed on this field)
    if order == "desc":
        query = query.order_by(ImageEntry.created_at.desc(), ImageEntry.hash.desc())
    else:
        query = query.order_by(ImageEntry.created_at.asc(), ImageEntry.hash.asc())

    # --- Fetch limit+1 to detect next page ---
    rows = query.limit(limit + 1).all()

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        # Skip entries with null created_at in keyset — they cannot be paginated
        if last.created_at is not None:
            next_cursor = _encode_cursor(last.created_at, last.hash)

    return {
        "items": [_entry_to_dict(e) for e in items],
        "next_cursor": next_cursor,
    }
