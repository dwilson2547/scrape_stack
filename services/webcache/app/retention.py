"""Bucket retention: enforce per-bucket entry/byte limits.

A bucket config (see models.BucketConfig) caps a bucket at `max_entries` rows
and/or `max_total_bytes` of compressed content. Enforcement keeps the NEWEST
entries (created_at desc) and evicts the oldest — a "latest N" rolling window.

Called automatically after every successful store (cheap: one config lookup
plus, when a limit is exceeded, deletion of the overflow) and manually via
POST /buckets/{bucket}/enforce (for retro-fitting a limit onto a bucket that
is already over it).
"""

import logging

from sqlalchemy.orm import Session

from . import metrics
from .models import BucketConfig, CacheEntry
from .storage import get_storage

log = logging.getLogger(__name__)


def enforce_bucket_limits(db: Session, bucket: str) -> int:
    """Evict oldest entries until `bucket` is within its configured limits.

    Returns the number of entries evicted. Buckets without a config are
    untouched. Storage files are deleted only when no remaining row still
    references the same (bucket, content_hash, prefix).
    """
    cfg = db.get(BucketConfig, bucket)
    if cfg is None or (cfg.max_entries is None and cfg.max_total_bytes is None):
        return 0

    entries = (
        db.query(CacheEntry)
        .filter(CacheEntry.bucket == bucket)
        .order_by(CacheEntry.created_at.desc(), CacheEntry.id.desc())
        .all()
    )

    doomed: list[CacheEntry] = []
    count = 0
    total_bytes = 0
    for entry in entries:
        count += 1
        total_bytes += entry.size_bytes or 0
        over_entries = cfg.max_entries is not None and count > cfg.max_entries
        over_bytes = cfg.max_total_bytes is not None and total_bytes > cfg.max_total_bytes
        if over_entries or over_bytes:
            doomed.append(entry)

    if not doomed:
        return 0

    storage = get_storage()
    for entry in doomed:
        still_referenced = (
            db.query(CacheEntry)
            .filter(
                CacheEntry.bucket == entry.bucket,
                CacheEntry.content_hash == entry.content_hash,
                CacheEntry.prefix == entry.prefix,
                CacheEntry.id != entry.id,
            )
            .first()
        )
        if still_referenced is None:
            storage.delete(entry.bucket, entry.content_hash, prefix=entry.prefix)
        db.delete(entry)

    db.commit()
    metrics.evicted_total.add(len(doomed), {"bucket": bucket})
    log.info("Bucket %r over limit: evicted %d oldest entries.", bucket, len(doomed))
    return len(doomed)
