from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import blake3
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Config
from . import metrics
from .models import UrlMap, Video
from .storage.base import VideoStore


_EXT_MIME: dict[str, str] = {
    ".mp4":  "video/mp4",
    ".gif":  "image/gif",
    ".webm": "video/webm",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".m4v":  "video/x-m4v",
}


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in _EXT_MIME:
        if path.endswith(ext):
            return ext
    return ".mp4"


def _ext_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in _EXT_MIME else ".mp4"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestResult:
    hash: str
    status: str        # "new" | "duplicate"
    file_path: str
    size_bytes: int = 0
    phash_distance: int | None = None


# ------------------------------------------------------------------ #
# Hashing helpers (CPU-bound — caller wraps in asyncio.to_thread)     #
# ------------------------------------------------------------------ #

def _compute_blake3(path: Path) -> str:
    hasher = blake3.blake3()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _compute_phash(path: Path) -> str | None:
    """Return a hex pHash string using videohash (wraps ffmpeg).

    Returns *None* if hashing fails for any reason (missing ffmpeg, etc.).
    """
    try:
        from videohash import VideoHash  # lazy import — optional dependency

        vh = VideoHash(path=str(path))
        raw: str = vh.hash  # e.g. "0b10101010..."
        if raw.startswith("0b"):
            raw = raw[2:]
        if not raw:
            return None
        padded = raw.zfill((len(raw) + 3) // 4 * 4)
        return format(int(padded, 2), "0x").zfill(len(padded) // 4)
    except Exception:  # noqa: BLE001
        return None


def _hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def _get_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ #
# URL map upsert                                                       #
# ------------------------------------------------------------------ #

def _upsert_url(db: Session, url: str, content_hash: str) -> None:
    latest = (
        db.query(UrlMap)
        .filter(UrlMap.url == url)
        .order_by(UrlMap.id.desc())
        .first()
    )
    if latest and latest.hash == content_hash:
        latest.seen_at = _utcnow()
        return
    db.add(UrlMap(url=url, hash=content_hash, seen_at=_utcnow()))


# ------------------------------------------------------------------ #
# Main pipeline (sync — caller wraps in asyncio.to_thread)            #
# ------------------------------------------------------------------ #

def run_pipeline(
    temp_path: Path,
    url: str,
    bucket: str,
    prefix: str | None,
    meta: dict | None,
    config: Config,
    db: Session,
    store: VideoStore,
    filename: str | None = None,
    client_name: str | None = None,
) -> IngestResult:
    """Hash, dedup-check, store, and index a video from an already-downloaded temp file.

    The caller is responsible for writing bytes to temp_path before calling
    this function and for deleting it afterwards.
    """
    # ---- Stage 1: BLAKE3 exact hash --------------------------------------
    content_hash = _compute_blake3(temp_path)

    existing = db.get(Video, content_hash)
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

    # ---- Stage 2: perceptual hash ----------------------------------------
    phash = _compute_phash(temp_path)

    phash_distance: int | None = None
    phash_match_hash: str | None = None

    if phash is not None:
        stored = [(v.hash, v.phash) for v in db.query(Video).filter(Video.phash.isnot(None)).all()]
        for stored_hash, stored_phash in stored:
            try:
                dist = _hamming(phash, stored_phash)
            except (ValueError, TypeError):
                continue
            if dist <= config.dedup.phash_threshold:
                if phash_distance is None or dist < phash_distance:
                    phash_distance = dist
                    phash_match_hash = stored_hash

    if phash_match_hash is not None:
        match = db.get(Video, phash_match_hash)
        if match:
            match.retrieved_at = _utcnow()
        _upsert_url(db, url, phash_match_hash)
        db.commit()
        if phash_distance is not None:
            metrics.phash_distance.record(phash_distance)
        return IngestResult(
            hash=phash_match_hash,
            status="duplicate",
            file_path=match.file_path if match else "",
            size_bytes=(match.size_bytes or 0) if match else 0,
            phash_distance=phash_distance,
        )

    # ---- New content: persist to store and index -------------------------
    size = temp_path.stat().st_size
    duration = _get_duration(temp_path)
    metrics.video_bytes.record(size)
    if duration is not None:
        metrics.video_duration_seconds.record(duration)
    meta_json = json.dumps(meta) if meta else None

    if filename:
        ext = _ext_from_filename(filename)
    else:
        ext = _ext_from_url(url)
    mime_type = _EXT_MIME.get(ext, "video/mp4")

    with open(temp_path, "rb") as stream:
        file_path = store.put(bucket, prefix or "", content_hash, stream, size, ext)

    now = _utcnow()
    try:
        db.add(Video(
            hash=content_hash,
            phash=phash,
            file_path=file_path,
            bucket=bucket,
            prefix=prefix,
            size_bytes=size,
            duration_s=duration,
            mime_type=mime_type,
            filename=filename,
            created_at=now,
            retrieved_at=now,
            source_url=url,
            meta_json=meta_json,
            client_name=client_name,
        ))
        db.flush()  # ensure videos row exists before url_map FK reference
        _upsert_url(db, url, content_hash)
        db.commit()
    except IntegrityError:
        # A concurrent request inserted the same hash first. The file on disk is
        # content-addressed (same bytes, same path), so don't delete it.
        db.rollback()
        existing = db.get(Video, content_hash)
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
        store.delete(bucket, prefix or "", content_hash, ext)
        raise
    except Exception:
        store.delete(bucket, prefix or "", content_hash, ext)
        raise

    return IngestResult(
        hash=content_hash,
        status="new",
        file_path=file_path,
        size_bytes=size,
    )
