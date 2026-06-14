import json
import os
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional

import blake3
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app import metrics as m
from app.database import get_session
from app.models import ImageEntry
from app.perceptual import compute_dhash
from app.schemas import ImageEntryOut
from app.storage import get_storage

router = APIRouter()


# ---------------------------------------------------------------------- #
# Helpers                                                                  #
# ---------------------------------------------------------------------- #

def _content_type_from_bytes(data: bytes) -> str:
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        mapping = {
            "JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif",
            "WEBP": "image/webp", "BMP": "image/bmp", "TIFF": "image/tiff",
            "ICO": "image/x-icon",
        }
        if img.format in mapping:
            return mapping[img.format]
    except Exception:
        pass
    try:
        snippet = data[:512].decode("utf-8", errors="ignore")
        if "<svg" in snippet or "<?xml" in snippet.lower():
            return "image/svg+xml"
    except Exception:
        pass
    return "application/octet-stream"


def _get_dimensions(data: bytes):
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.size
    except Exception:
        return None, None


_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/tiff": ".tiff",
    "image/x-icon": ".ico", "image/svg+xml": ".svg",
}


def _storage_key(bucket: str, content_hash: str, file_extension: Optional[str],
                 prefix: Optional[str] = None) -> str:
    shard_a = content_hash[:2]
    shard_b = content_hash[2:4]
    filename = content_hash + (file_extension or "")
    parts = [p for p in [bucket, prefix] if p]
    parts += [shard_a, shard_b, filename]
    return "/".join(parts)


def _original_filename(url: str) -> Optional[str]:
    try:
        name = os.path.basename(urllib.parse.urlparse(url).path).split("?")[0]
        return name or None
    except Exception:
        return None


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------- #
# NOTE: specific /cache/* paths must be registered before /cache/{hash}  #
# ---------------------------------------------------------------------- #

@router.get("/cache/meta/{hash}", response_model=ImageEntryOut)
def get_meta(hash: str, bucket: str = "", db: Session = Depends(get_session)):
    entry = db.query(ImageEntry).filter(
        ImageEntry.bucket == bucket, ImageEntry.hash == hash
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    return entry


@router.get("/cache/lookup", response_model=ImageEntryOut)
def lookup(
    url: str,
    bucket: Optional[str] = None,
    max_age: Optional[int] = None,
    version: Optional[str] = None,
    db: Session = Depends(get_session),
):
    if max_age is not None and version is not None:
        raise HTTPException(status_code=422, detail="max_age and version are mutually exclusive")

    if version is not None:
        entry = db.query(ImageEntry).filter(ImageEntry.hash == version).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Version not found")
        m.lookup_counter.add(1, {"result": "hit"})
        return entry

    q = db.query(ImageEntry).filter(ImageEntry.url == url)
    if bucket is not None:
        q = q.filter(ImageEntry.bucket == bucket)
    entry = q.order_by(ImageEntry.created_at.desc()).first()
    if not entry:
        m.lookup_counter.add(1, {"result": "miss"})
        raise HTTPException(status_code=404, detail="Not found")

    if max_age is not None:
        ts = entry.retrieved_at or entry.created_at
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > max_age:
                m.lookup_counter.add(1, {"result": "miss"})
                raise HTTPException(status_code=404, detail="Cache entry exceeds max_age")

    m.lookup_counter.add(1, {"result": "hit"})
    return entry


@router.get("/cache/search", response_model=List[ImageEntryOut])
def search(url_contains: str, bucket: Optional[str] = None, db: Session = Depends(get_session)):
    q = db.query(ImageEntry).filter(ImageEntry.url.contains(url_contains))
    if bucket is not None:
        q = q.filter(ImageEntry.bucket == bucket)
    return q.all()


@router.get("/cache/similar", response_model=List[ImageEntryOut])
def similar(
    perceptual_hash: str,
    max_hamming_distance: int = 4,
    bucket: Optional[str] = None,
    db: Session = Depends(get_session),
):
    m.similar_search_counter.add(1)
    query_int = int(perceptual_hash, 16)
    results = []
    q = db.query(ImageEntry).filter(ImageEntry.perceptual_hash != None)
    if bucket is not None:
        q = q.filter(ImageEntry.bucket == bucket)
    for entry in q.all():
        try:
            dist = bin(query_int ^ int(entry.perceptual_hash, 16)).count("1")
            if dist <= max_hamming_distance:
                results.append(entry)
        except Exception:
            continue
    return results


@router.get("/cache/resolve")
def resolve(url: str, bucket: Optional[str] = None, db: Session = Depends(get_session)):
    q = db.query(ImageEntry).filter(ImageEntry.url == url)
    if bucket is not None:
        q = q.filter(ImageEntry.bucket == bucket)
    entry = q.order_by(ImageEntry.created_at.desc()).first()
    if not entry:
        raise HTTPException(status_code=404, detail="URL not found")
    return {"hash": entry.hash, "url": url}


@router.get("/cache/serve/{hash}")
def serve_image(
    hash: str,
    request: Request,
    bucket: str = "",
    prefix: str = "",
    db: Session = Depends(get_session),
):
    entry = db.query(ImageEntry).filter(
        ImageEntry.bucket == bucket, ImageEntry.hash == hash
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")

    etag = f'"{hash}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    data = get_storage().read(_storage_key(bucket, hash, entry.file_extension, entry.prefix or None))

    def _chunks(d: bytes, size: int = 65536):
        for i in range(0, len(d), size):
            yield d[i:i + size]

    return StreamingResponse(
        _chunks(data),
        media_type=entry.mime_type,
        headers={"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/cache/{hash}")
def get_image(hash: str, bucket: str = "", db: Session = Depends(get_session)):
    entry = db.query(ImageEntry).filter(
        ImageEntry.bucket == bucket, ImageEntry.hash == hash
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    data = get_storage().read(_storage_key(bucket, hash, entry.file_extension, entry.prefix or None))
    return Response(content=data, media_type=entry.mime_type)


@router.delete("/cache/{hash}", status_code=204)
def delete_image(hash: str, bucket: str = "", db: Session = Depends(get_session)):
    entry = db.query(ImageEntry).filter(
        ImageEntry.bucket == bucket, ImageEntry.hash == hash
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    get_storage().delete(_storage_key(bucket, hash, entry.file_extension, entry.prefix or None))
    db.delete(entry)
    db.commit()


@router.post("/cache", status_code=201)
async def store_image(
    file: UploadFile = File(...),
    url: str = Form(...),
    client_name: str = Form(...),
    content_hash: str = Form(...),
    bucket: str = Form(""),
    prefix: str | None = Form(None),
    meta: Optional[str] = Form(None),
    db: Session = Depends(get_session),
):
    import hashlib
    data = await file.read()

    # Verify the provided hash matches the actual content
    actual_hash = blake3.blake3(data).hexdigest()
    if actual_hash != content_hash:
        raise HTTPException(status_code=422, detail="content_hash does not match uploaded content")

    existing = db.query(ImageEntry).filter(
        ImageEntry.bucket == bucket, ImageEntry.hash == content_hash
    ).first()
    if existing:
        existing.retrieved_at = _utcnow()
        db.commit()
        db.refresh(existing)
        m.store_counter.add(1, {"result": "duplicate"})
        return JSONResponse(content=jsonable_encoder(ImageEntryOut.model_validate(existing)), status_code=200)

    mime_type = _content_type_from_bytes(data)
    if not mime_type.startswith("image/"):
        raise HTTPException(
            status_code=422,
            detail=f"Rejected: content resolved to '{mime_type}', not an image.",
        )

    width, height = _get_dimensions(data)
    phash = compute_dhash(data)
    m.perceptual_hash_counter.add(1, {"result": "ok" if phash else "failed"})
    m.image_bytes_histogram.record(len(data))

    file_extension = _CONTENT_TYPE_EXT.get(mime_type, "")
    orig_filename = _original_filename(url)

    entry = ImageEntry(
        bucket=bucket,
        prefix=prefix or None,
        url=url,
        hash=content_hash,
        mime_type=mime_type,
        size_bytes=len(data),
        filename=orig_filename,
        width=width,
        height=height,
        perceptual_hash=phash,
        file_extension=file_extension or None,
        client_name=client_name,
        created_at=_utcnow(),
        retrieved_at=_utcnow(),
        meta_json=meta,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    get_storage().write(_storage_key(bucket, content_hash, file_extension or None, prefix or None), data)
    m.store_counter.add(1, {"result": "new"})

    return JSONResponse(content=jsonable_encoder(ImageEntryOut.model_validate(entry)), status_code=201)
