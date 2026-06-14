# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Client (scraper)                                            │
│  webcache_client.WebCacheClient  or  raw HTTP                │
└──────────────────────┬───────────────────────────────────────┘
                       │ REST / JSON
┌──────────────────────▼───────────────────────────────────────┐
│  FastAPI service  (app/main.py)                              │
│                                                              │
│  POST /cache   GET /cache   GET /cache/search   DELETE …     │
└──────┬──────────────────────────────────┬────────────────────┘
       │ SQLAlchemy ORM                   │ BaseStorage
┌──────▼──────────┐               ┌───────▼────────────────────┐
│  SQLite DB      │               │  LocalStorage  or S3Storage│
│  (cache_entries)│               │  (one .lz4 file per page)  │
└─────────────────┘               └────────────────────────────┘
```

## Key design decisions

### Deduplication via content hash
Every stored page is identified by the BLAKE2b-256 hash of its raw content.
If two requests arrive with identical content the file is written once;
the second request returns HTTP 200 (already cached).

### LZ4 compression
Each file on disk / in S3 is LZ4-compressed.  LZ4 was chosen for its
extremely fast decompression speed, which keeps latency low when
retrieving pages.

### Single storage backend
The service is configured to use *either* local disk or S3/MinIO, never both.
This eliminates any possibility of the two stores going out of sync.
Switch via the `STORAGE_BACKEND` environment variable (`local` or `s3`).

### Storage backend abstraction
`app/storage/base.py` defines `BaseStorage` (write / read / delete / exists).
Both `LocalStorage` and `S3Storage` implement this interface so the route
layer is completely decoupled from the underlying storage medium.

### Database
SQLAlchemy + SQLite is used by default.  The `DATABASE_URL` env var accepts
any SQLAlchemy connection string, making it straightforward to migrate to
PostgreSQL later without code changes.

## File layout

```
webcache/
├── app/
│   ├── main.py            FastAPI app + table creation
│   ├── config.py          Pydantic Settings (env / .env file)
│   ├── database.py        SQLAlchemy engine & session factory
│   ├── models.py          ORM model (CacheEntry)
│   ├── schemas.py         Pydantic request / response models
│   ├── routes/
│   │   └── cache.py       All /cache endpoints
│   └── storage/
│       ├── base.py        Abstract BaseStorage
│       ├── local.py       Disk-backed implementation
│       └── s3.py          S3 / MinIO implementation
├── client/
│   ├── webcache_client.py Python client class
│   └── setup.py           pip-installable package
├── tests/
│   ├── conftest.py        Fixtures (in-memory DB, tmp storage, MinIO testcontainer)
│   ├── test_api.py        Full API integration tests (local storage)
│   ├── test_storage_local.py  Unit tests for LocalStorage
│   └── test_storage_s3.py     Integration tests via MinIO testcontainer
├── docs/
│   ├── api.md             Endpoint reference
│   └── architecture.md    This file
├── Dockerfile
├── docker-compose.yml     Local-only deployment (./data volume)
├── requirements.txt
├── requirements-dev.txt   Test dependencies
└── .env.example
```

## Running locally

```bash
# Build & start
docker compose up --build

# Cache a page
curl -X POST http://localhost:8000/cache \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","content":"<html>…</html>","client_name":"curl","lookup_time":"2024-01-01T00:00:00"}'

# Retrieve it
curl "http://localhost:8000/cache?url=https://example.com"
```

## Running tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/
```

S3 tests require Docker; they are skipped automatically when Docker or
`testcontainers[minio]` is unavailable.
