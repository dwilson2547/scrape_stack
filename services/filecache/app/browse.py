import base64
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .database import get_db
from .models import File, UrlMap


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

def _file_to_browse_dict(file: File, url: str | None) -> dict[str, Any]:
    return {
        "hash": file.hash,
        "url": url,
        "filename": file.filename,
        "bucket": file.bucket,
        "prefix": file.prefix,
        "client_name": file.client_name,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "created_at": file.created_at.isoformat(),
        "retrieved_at": file.retrieved_at.isoformat() if file.retrieved_at else None,
        "cache_type": "file",
    }


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_browse_router() -> APIRouter:
    router = APIRouter(tags=["browse"])

    @router.get("/browse/buckets")
    def list_buckets(db: Session = Depends(get_db)):
        """List all distinct bucket names."""
        rows = db.query(File.bucket).distinct().order_by(File.bucket).all()
        return {"buckets": [r[0] for r in rows]}

    @router.get("/browse/prefixes")
    def list_prefixes(
        bucket: str = Query(..., description="Bucket to list prefixes for"),
        db: Session = Depends(get_db),
    ):
        """List all distinct prefixes within a bucket."""
        rows = (
            db.query(File.prefix)
            .filter(File.bucket == bucket)
            .distinct()
            .order_by(File.prefix)
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
        Paginated list of file records with optional filters and cursor-based pagination.

        Uses a correlated subquery to resolve the most recently seen URL per file hash.
        """
        # Correlated subquery: latest URL for each File row
        latest_url_sq = (
            db.query(UrlMap.url)
            .filter(UrlMap.hash == File.hash)
            .order_by(UrlMap.seen_at.desc())
            .limit(1)
            .correlate(File)
            .scalar_subquery()
        )

        query = db.query(File, latest_url_sq.label("url"))

        # --- Static filters ---
        if bucket is not None:
            query = query.filter(File.bucket == bucket)
        if prefix is not None:
            query = query.filter(File.prefix == prefix)
        if client_name is not None:
            query = query.filter(File.client_name == client_name)
        if date_from is not None:
            query = query.filter(File.created_at >= date_from)
        if date_to is not None:
            query = query.filter(File.created_at <= date_to)
        if q is not None:
            # Filter on the correlated URL subquery via a separate exists/ilike filter
            url_match_sq = (
                db.query(UrlMap.url)
                .filter(UrlMap.hash == File.hash)
                .filter(UrlMap.url.ilike(f"%{q}%"))
                .correlate(File)
                .exists()
            )
            query = query.filter(url_match_sq)

        # --- Cursor / keyset pagination ---
        if cursor is not None:
            cursor_ts, cursor_hash = _decode_cursor(cursor)
            if order == "desc":
                query = query.filter(
                    or_(
                        File.created_at < cursor_ts,
                        and_(
                            File.created_at == cursor_ts,
                            File.hash < cursor_hash,
                        ),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        File.created_at > cursor_ts,
                        and_(
                            File.created_at == cursor_ts,
                            File.hash > cursor_hash,
                        ),
                    )
                )

        # --- Ordering ---
        if order == "desc":
            query = query.order_by(File.created_at.desc(), File.hash.desc())
        else:
            query = query.order_by(File.created_at.asc(), File.hash.asc())

        # --- Fetch limit+1 to detect next page ---
        rows = query.limit(limit + 1).all()

        has_more = len(rows) > limit
        items = rows[:limit]

        next_cursor = None
        if has_more and items:
            last_file, _ = items[-1]
            next_cursor = _encode_cursor(last_file.created_at, last_file.hash)

        return {
            "items": [_file_to_browse_dict(file, url) for file, url in items],
            "next_cursor": next_cursor,
        }

    return router
