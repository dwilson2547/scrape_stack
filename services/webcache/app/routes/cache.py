import blake3
from datetime import datetime, timedelta, UTC

import lz4.frame
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from .. import metrics
from ..database import get_db
from ..models import CacheEntry
from ..schemas import CacheEntryCreate, CacheEntryFull, CacheEntryMeta
from ..storage import get_storage

router = APIRouter(prefix="/cache", tags=["cache"])


def _compute_hash(content: str) -> str:
    return blake3.blake3(content.encode()).hexdigest()


def _decompress(bucket: str, content_hash: str, prefix: str | None = None) -> str:
    storage = get_storage()
    try:
        compressed = storage.read(bucket, content_hash, prefix=prefix)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cache file not found")
    return lz4.frame.decompress(compressed).decode()


# NOTE: specific /cache/* paths must be registered before /cache/{content_hash}

@router.get("/lookup", response_model=CacheEntryMeta)
def lookup(
    url: str,
    bucket: str = "default",
    max_age: int | None = None,
    version: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Return metadata (no content) for a cached URL.
    version (content_hash) and max_age are mutually exclusive.
    """
    if max_age is not None and version is not None:
        raise HTTPException(status_code=422, detail="max_age and version are mutually exclusive")

    if version is not None:
        entry = db.query(CacheEntry).filter(
            CacheEntry.bucket == bucket,
            CacheEntry.content_hash == version,
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Version not found")
        metrics.lookup_total.add(1, {"result": "hit"})
        return entry

    entry = (
        db.query(CacheEntry)
        .filter(CacheEntry.url == url, CacheEntry.bucket == bucket)
        .order_by(CacheEntry.created_at.desc())
        .first()
    )
    if not entry:
        metrics.lookup_total.add(1, {"result": "miss"})
        raise HTTPException(status_code=404, detail="Cache entry not found")

    if max_age is not None:
        ts = entry.retrieved_at or entry.created_at
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - ts).total_seconds()
            if age > max_age:
                metrics.lookup_total.add(1, {"result": "miss"})
                raise HTTPException(status_code=404, detail="Cache entry exceeds max_age")

    metrics.lookup_total.add(1, {"result": "hit"})
    return entry


@router.get("/search", response_model=list[CacheEntryMeta])
def search_by_url(url_contains: str, bucket: str = "default", db: Session = Depends(get_db)):
    """Return metadata for all entries in a bucket whose URL contains `url_contains`."""
    entries = (
        db.query(CacheEntry)
        .filter(CacheEntry.bucket == bucket, CacheEntry.url.contains(url_contains))
        .order_by(CacheEntry.created_at.desc())
        .all()
    )
    return entries


@router.get("/serve/{content_hash}")
def serve_page(
    content_hash: str,
    request: Request,
    bucket: str = "default",
    db: Session = Depends(get_db),
):
    """Serve raw decompressed HTML with ETag and immutable cache headers."""
    entry = db.query(CacheEntry).filter(
        CacheEntry.content_hash == content_hash,
        CacheEntry.bucket == bucket,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cache entry not found")

    etag = f'"{content_hash}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    content = _decompress(entry.bucket, entry.content_hash, prefix=entry.prefix)

    def _chunks(text: str, size: int = 65536):
        for i in range(0, len(text), size):
            yield text[i:i + size].encode()

    return StreamingResponse(
        _chunks(content),
        media_type="text/html; charset=utf-8",
        headers={"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/meta/{content_hash}", response_model=CacheEntryMeta)
def get_meta(content_hash: str, bucket: str = "default", db: Session = Depends(get_db)):
    """Return metadata for a cached entry by its content hash (no content body)."""
    entry = db.query(CacheEntry).filter(
        CacheEntry.content_hash == content_hash,
        CacheEntry.bucket == bucket,
    ).first()
    if not entry:
        metrics.lookup_total.add(1, {"result": "miss"})
        raise HTTPException(status_code=404, detail="Cache entry not found")
    metrics.lookup_total.add(1, {"result": "hit"})
    return entry


@router.get("", response_model=CacheEntryFull)
def get_by_url(
    url: str,
    bucket: str = "default",
    max_age: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Return the most recent cached entry for a URL, including content.
    If max_age (seconds) is given, entries older than that threshold return 404.
    """
    entry = (
        db.query(CacheEntry)
        .filter(CacheEntry.url == url, CacheEntry.bucket == bucket)
        .order_by(CacheEntry.created_at.desc())
        .first()
    )
    if not entry:
        metrics.lookup_total.add(1, {"result": "miss"})
        raise HTTPException(status_code=404, detail="Cache entry not found")

    if max_age is not None:
        ts = entry.retrieved_at or entry.created_at
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - ts).total_seconds()
            if age > max_age:
                metrics.lookup_total.add(1, {"result": "miss"})
                raise HTTPException(status_code=404, detail="Cache entry exceeds max_age")

    content = _decompress(entry.bucket, entry.content_hash, prefix=entry.prefix)
    metrics.lookup_total.add(1, {"result": "hit"})
    return CacheEntryFull(**CacheEntryMeta.model_validate(entry).model_dump(), content=content)


@router.get("/{content_hash}", response_model=CacheEntryFull)
def get_by_hash(content_hash: str, bucket: str = "default", db: Session = Depends(get_db)):
    """Return a specific cached entry by its content hash."""
    entry = db.query(CacheEntry).filter(
        CacheEntry.content_hash == content_hash,
        CacheEntry.bucket == bucket,
    ).first()
    if not entry:
        metrics.lookup_total.add(1, {"result": "miss"})
        raise HTTPException(status_code=404, detail="Cache entry not found")

    content = _decompress(entry.bucket, entry.content_hash, prefix=entry.prefix)
    metrics.lookup_total.add(1, {"result": "hit"})
    return CacheEntryFull(**CacheEntryMeta.model_validate(entry).model_dump(), content=content)


@router.delete("/{content_hash}", status_code=204)
def delete_entry(content_hash: str, bucket: str = "default", db: Session = Depends(get_db)):
    """Delete a cached entry and its associated file."""
    entry = db.query(CacheEntry).filter(
        CacheEntry.content_hash == content_hash,
        CacheEntry.bucket == bucket,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cache entry not found")

    get_storage().delete(entry.bucket, entry.content_hash, prefix=entry.prefix)
    db.delete(entry)
    db.commit()


@router.post("", response_model=CacheEntryMeta, status_code=201)
def store_page(entry: CacheEntryCreate, db: Session = Depends(get_db)):
    """
    Store a web page. content_hash must be pre-computed by the client (BLAKE3).
    Returns 200 if (url, bucket, content_hash) already exists; 201 on new entry.
    Storage file is reused if the hash is already stored.
    """
    actual_hash = _compute_hash(entry.content)
    if actual_hash != entry.content_hash:
        raise HTTPException(status_code=422, detail="content_hash does not match content")

    existing = db.query(CacheEntry).filter(
        CacheEntry.bucket == entry.bucket,
        CacheEntry.url == entry.url,
        CacheEntry.content_hash == entry.content_hash,
    ).first()
    if existing:
        existing.retrieved_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing)
        metrics.store_total.add(1, {"result": "duplicate"})
        return JSONResponse(
            content=jsonable_encoder(CacheEntryMeta.model_validate(existing)),
            status_code=200,
        )

    compressed = lz4.frame.compress(entry.content.encode())
    storage = get_storage()
    if not storage.exists(entry.bucket, entry.content_hash, prefix=entry.prefix):
        metrics.compressed_bytes.record(len(compressed))
        storage.write(entry.bucket, entry.content_hash, compressed, prefix=entry.prefix)

    now = datetime.now(UTC)
    db_entry = CacheEntry(
        url=entry.url,
        bucket=entry.bucket,
        prefix=entry.prefix,
        content_hash=entry.content_hash,
        client_name=entry.client_name,
        created_at=now,
        retrieved_at=now,
    )
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    metrics.store_total.add(1, {"result": "created"})
    return db_entry
