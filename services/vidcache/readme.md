# vidcache

Content-addressed video cache service.  Deduplicates and persists video content where the same video is frequently re-uploaded under different URLs.

## Features

- **Two-stage deduplication** — URL fast-path → BLAKE3 exact hash → perceptual hash (pHash via ffmpeg)
- **Pluggable storage** — swap between local filesystem and S3-compatible stores (MinIO, AWS S3) with a single config line
- **Streaming ingest** — never buffers full video payloads in memory; supports files from a few MB to 1 GB+
- **Byte-range reads** — `Range:` header support for seeking and partial content delivery (HTTP 206)
- **SQLite index** — canonical dedup index and metadata store, backend-agnostic

## Requirements

- Python 3.11+
- `ffmpeg` available on `PATH` (used by `videohash` for perceptual hashing)

```
pip install -r requirements.txt
```

## Configuration

Copy `config.yaml` and edit as needed:

```yaml
video_store:
  backend: local          # or: s3

  local:
    root: /data/vidcache

  s3:
    endpoint: http://minio.home:9000
    access_key: minioadmin
    secret_key: minioadmin
    region: us-east-1

dedup:
  phash_threshold: 10

index:
  db_path: /data/vidcache/index.db

server:
  host: 0.0.0.0
  port: 8765
```

## Running

```bash
python main.py --config config.yaml
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest` | Submit a video URL for caching |
| `GET` | `/video/{hash}` | Retrieve video by content hash (supports `Range`) |
| `GET` | `/resolve?url=…` | Resolve a URL to its hash |
| `GET` | `/meta/{hash}` | Retrieve metadata + all known URL aliases |
| `DELETE` | `/video/{hash}` | Delete a cached video |

### POST /ingest

```json
{
  "url":    "https://example.com/video/abc123",
  "bucket": "videos",
  "prefix": "archive",
  "meta":   { "title": "…" }
}
```

Response:

```json
{
  "hash":   "abcdef1234…",
  "status": "new",
  "file_path": "videos/archive/ab/cd/abcdef1234….mp4",
  "phash_distance": 0
}
```

`status` is one of `new`, `duplicate` (BLAKE3 or pHash match), or `url_alias` (URL already seen).

## Storage layout

```
<root>/<bucket>/<prefix>/<hash[:2]>/<hash[2:4]>/<hash>.mp4
```

Both local and S3 backends use the same logical layout — `file_path` values in the SQLite index are backend-agnostic.

## Local → S3 migration

```bash
# Dry run first
python migrate_to_s3.py --config config.yaml --dry-run

# Migrate
python migrate_to_s3.py --config config.yaml
```

Then update `config.yaml` to set `backend: s3` and restart.

## Project structure

```
vidcache/
├── main.py              # entry point
├── config.yaml          # sample configuration
├── requirements.txt
├── migrate_to_s3.py     # local → S3 migration helper
└── app/
    ├── api.py           # FastAPI routes
    ├── config.py        # config dataclasses + YAML loader
    ├── db.py            # aiosqlite database layer
    ├── dedup.py         # deduplication pipeline
    └── storage/
        ├── base.py      # VideoStore Protocol
        ├── local.py     # local filesystem backend
        └── s3.py        # S3 / MinIO backend
```
