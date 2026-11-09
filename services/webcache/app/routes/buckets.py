"""Bucket configuration and retention management.

Buckets are created implicitly by stores (the column always existed); this
router adds the retention layer: per-bucket `max_entries` / `max_total_bytes`
limits with automatic eviction of the oldest entries after every store, plus
a manual enforce endpoint for retro-fitting limits onto existing buckets.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BucketConfig, CacheEntry
from ..retention import enforce_bucket_limits
from ..schemas import BucketConfigResponse, BucketConfigUpdate, BucketStats

router = APIRouter(prefix="/buckets", tags=["buckets"])


def _validate(bucket: str, cfg: BucketConfigUpdate) -> None:
    if not bucket or not bucket.strip():
        raise HTTPException(status_code=422, detail="Bucket name must not be empty")
    if cfg.max_entries is not None and cfg.max_entries < 1:
        raise HTTPException(status_code=422, detail="max_entries must be >= 1")
    if cfg.max_total_bytes is not None and cfg.max_total_bytes < 1:
        raise HTTPException(status_code=422, detail="max_total_bytes must be >= 1")


def _stats(db: Session, bucket: str) -> BucketStats:
    row = db.query(
        func.count(CacheEntry.id),
        func.coalesce(func.sum(CacheEntry.size_bytes), 0),
    ).filter(CacheEntry.bucket == bucket).one()
    return BucketStats(entries=row[0], total_bytes=row[1])


def _response(db: Session, cfg: BucketConfig) -> BucketConfigResponse:
    return BucketConfigResponse(
        bucket=cfg.bucket,
        max_entries=cfg.max_entries,
        max_total_bytes=cfg.max_total_bytes,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
        stats=_stats(db, cfg.bucket),
    )


@router.get("", response_model=list[BucketConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    """List all bucket configs with live stats."""
    return [_response(db, cfg) for cfg in db.query(BucketConfig).order_by(BucketConfig.bucket).all()]


@router.put("/{bucket}", response_model=BucketConfigResponse)
def upsert_config(bucket: str, cfg: BucketConfigUpdate, db: Session = Depends(get_db)):
    """Create or update a bucket's retention config and enforce it immediately."""
    _validate(bucket, cfg)
    existing = db.get(BucketConfig, bucket)
    if existing is None:
        existing = BucketConfig(
            bucket=bucket,
            max_entries=cfg.max_entries,
            max_total_bytes=cfg.max_total_bytes,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(existing)
    else:
        existing.max_entries = cfg.max_entries
        existing.max_total_bytes = cfg.max_total_bytes
        existing.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(existing)
    enforce_bucket_limits(db, bucket)
    db.refresh(existing)
    return _response(db, existing)


@router.post("/{bucket}/enforce")
def enforce(bucket: str, db: Session = Depends(get_db)):
    """Manually evict down to a bucket's configured limits.

    Useful after lowering a limit on a bucket that is already over it; the
    automatic enforcement only runs on store.
    """
    cfg = db.get(BucketConfig, bucket)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config for this bucket")
    evicted = enforce_bucket_limits(db, bucket)
    return {"bucket": bucket, "evicted": evicted}


@router.delete("/{bucket}", status_code=204)
def delete_config(bucket: str, db: Session = Depends(get_db)):
    """Remove a bucket's retention config. Entries are NOT deleted."""
    cfg = db.get(BucketConfig, bucket)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config for this bucket")
    db.delete(cfg)
    db.commit()
