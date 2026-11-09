from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import blake3

from .models import File, UrlMap
from .storage.base import BaseStorage


_EXT_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".tgz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
    ".7z": "application/x-7z-compressed",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".json": "application/json",
    ".csv": "text/csv",
    ".xml": "application/xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".bin": "application/octet-stream",
}


@dataclass
class IngestResult:
    hash: str
    status: str  # "new" | "duplicate"
    file_path: str
    size_bytes: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_blake3(path: Path) -> str:
    hasher = blake3.blake3()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def ext_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".bin"


def mime_from_ext(ext: str) -> str:
    return _EXT_MIME.get(ext, "application/octet-stream")


def _upsert_url(db, url: str, content_hash: str) -> None:
    latest = (
        db.query(UrlMap)
        .filter(UrlMap.url == url)
        .order_by(UrlMap.seen_at.desc())
        .first()
    )
    if latest and latest.hash == content_hash:
        return  # same URL, same hash — no new row needed
    db.add(UrlMap(url=url, hash=content_hash, seen_at=_utcnow()))


def run_ingest(
    temp_path: Path,
    url: str,
    bucket: str,
    filename: str,
    meta: dict[str, Any] | None,
    db,
    store: BaseStorage,
    prefix: str | None = None,
    client_name: str | None = None,
) -> IngestResult:
    """Hash, dedup-check, store, and index a file from a temp path.

    The caller is responsible for writing bytes to temp_path before calling
    this function and for deleting it afterwards.
    """
    content_hash = _compute_blake3(temp_path)

    existing = db.get(File, content_hash)
    if existing:
        existing.retrieved_at = _utcnow()
        _upsert_url(db, url, content_hash)
        db.commit()
        return IngestResult(
            hash=content_hash,
            status="duplicate",
            file_path=existing.file_path,
            size_bytes=existing.size_bytes or 0,
        )

    ext = ext_from_filename(filename)
    mime_type = mime_from_ext(ext)
    size_bytes = temp_path.stat().st_size
    now = _utcnow()

    with open(temp_path, "rb") as stream:
        file_path = store.write(bucket, prefix, content_hash, stream, ext)

    try:
        db.add(File(
            hash=content_hash,
            file_path=file_path,
            bucket=bucket,
            prefix=prefix,
            size_bytes=size_bytes,
            mime_type=mime_type,
            filename=filename,
            created_at=now,
            retrieved_at=now,
            meta_json=json.dumps(meta) if meta else None,
            client_name=client_name,
        ))
        _upsert_url(db, url, content_hash)
        db.commit()
    except Exception:
        store.delete(bucket, prefix, content_hash, ext)
        raise

    return IngestResult(
        hash=content_hash,
        status="new",
        file_path=file_path,
        size_bytes=size_bytes,
    )
