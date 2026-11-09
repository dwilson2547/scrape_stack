# imgcache — build instructions

Centralized cold storage cache for images fetched by web scrapers. Build the
project in this `imgcache/` folder. Include documentation in `docs/` and tests
in `tests/`.

---

## Overview

Images are binary blobs — do NOT apply LZ4 or any other compression. JPEG,
PNG, WebP, GIF and SVG are already compressed; re-compressing wastes CPU and
inflates file size. Store raw bytes, one file per image.

The primary goals are:
- Deduplication: the same image fetched by multiple scrapers is stored exactly once.
- A consistent, addressable storage point shared across many scraper processes.
- Rich metadata so downstream consumers can filter without fetching image bytes.
- Similarity detection: detect the same image reposted at a different resolution.

---

## Storage backends

Support two mutually exclusive backends configured via `STORAGE_BACKEND` env var:

- `local` — files written to a configurable local directory (default)
- `s3` — files written to an S3-compatible bucket (AWS or MinIO)

Never write to both simultaneously. Switching is done by changing the env var;
no code changes required. Use the same `BaseStorage` abstraction pattern
(write / read / delete / exists) with `LocalStorage` and `S3Storage`
implementations. Lazy-initialize the backend singleton so tests can inject a
replacement before the app module is imported.

---

## Database

Use SQLAlchemy as the ORM. Default to SQLite (`DATABASE_URL` env var). The
schema must remain compatible with PostgreSQL so that migrating later requires
only a connection-string change. Make the engine and session factory lazy
(initialized on first use, not at import time) so tests can inject an
in-memory SQLite engine via the same override pattern used in webcache.

### `image_entries` table columns

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | auto-increment |
| `url` | string | indexed — original URL the image was fetched from |
| `content_hash` | string(64) | BLAKE2b-256 hex of raw image bytes; unique; used as filename |
| `content_type` | string | MIME type, e.g. `image/jpeg` — stored at write time, returned as `Content-Type` on retrieval |
| `file_size_bytes` | integer | byte length of the raw image data |
| `original_filename` | string nullable | filename component parsed from the URL, best-effort |
| `width` | integer nullable | pixel width decoded from image at write time |
| `height` | integer nullable | pixel height decoded from image at write time |
| `perceptual_hash` | string(16) nullable | dHash hex string (see below) — used for similarity detection |
| `client_name` | string | name of the scraper or process that submitted the image |
| `lookup_time` | datetime | when the client fetched the image from origin |
| `created_at` | datetime | when this service stored the image (UTC, timezone-aware) |

---

## Hashing and deduplication

Compute a BLAKE2b-256 hash of the **raw image bytes** (before any processing).
Use the hex digest as the storage filename: `{content_hash}` (no extension
needed; content-type is in the DB). If an incoming image produces a hash that
already exists in the database return HTTP 200 with the existing metadata and
skip the write. New entries return HTTP 201.

---

## Perceptual hash (dot matrix / similarity detection)

Compute a **dHash** (difference hash) for every image at write time using the
`imagehash` library. dHash works on pixel-level differences and is
resolution-invariant — the same image scaled to 200×200 and 800×800 produces
the same or a very similar hash. Store the 16-character hex string in the
`perceptual_hash` column.

Expose a search endpoint that accepts a `perceptual_hash` query parameter and a
`max_hamming_distance` (default 4). Return all entries whose stored perceptual
hash differs from the query hash by at most `max_hamming_distance` bits (XOR
the two integers, count set bits). This enables callers to find near-duplicate
images across resolutions.

If the image cannot be decoded for hashing (e.g. SVG, corrupted file), store
`NULL` in `perceptual_hash` — do not fail the store request.

---

## API — REST/JSON + binary retrieval

Base prefix: no version prefix needed for now. Keep the service open (no auth).
Follow standard HTTP status codes: 404 when not found, 409 is not needed
(dedup is silent — use 200/201 distinction), 422 on validation error.

### Endpoints

#### `POST /images`
Store an image. Accept `multipart/form-data` with fields:
- `file` — the image binary (UploadFile)
- `url` — string
- `client_name` — string
- `lookup_time` — ISO 8601 datetime string

Compute content hash, perceptual hash, width/height, file size, and
content_type from the uploaded bytes. Return `ImageEntryMeta` (no bytes).
HTTP 201 on new store, HTTP 200 if already existed (same content hash).

#### `GET /images/{content_hash}`
Return the raw image bytes as a streaming response with the correct
`Content-Type` header. Do NOT base64-encode or JSON-wrap the bytes. HTTP 404
if hash not found.

#### `GET /images/meta/{content_hash}`
Return `ImageEntryMeta` JSON for a specific hash. HTTP 404 if not found.

#### `GET /images/lookup?url={url}`
Return the most recent `ImageEntryMeta` for an exact URL match. HTTP 404 if
not found.

#### `GET /images/search?url_contains={substring}`
Return a list of `ImageEntryMeta` for all entries whose URL contains the
substring. Returns empty list if no matches. Useful for querying all images
from a domain or path regardless of query parameters.

#### `GET /images/similar?perceptual_hash={hex}&max_hamming_distance={n}`
Return a list of `ImageEntryMeta` for all entries within `max_hamming_distance`
bits of the provided perceptual hash. Default `max_hamming_distance=4`.
Hamming distance is computed in Python (XOR + bit_count). Returns empty list if
no matches. Skip entries where `perceptual_hash` is NULL.

#### `DELETE /images/{content_hash}`
Delete the entry and its storage file. HTTP 204 on success, HTTP 404 if not
found.

#### `GET /health`
Returns `{"status": "ok"}`.

---

## Schemas

`ImageEntryMeta` — all DB columns except `id`, no binary data.

`ImageEntryFull` — not needed; binary is served directly via streaming response.

---

## Metrics — OpenTelemetry

Use the OpenTelemetry Python SDK. Do NOT use `prometheus-fastapi-instrumentator`
or `prometheus_client` directly. Export via OTLP gRPC to a collector
(`OTEL_EXPORTER_OTLP_ENDPOINT` env var, default `http://localhost:4317`).
Also expose a Prometheus scrape endpoint at `/metrics` using
`opentelemetry-exporter-prometheus` so the service can be scraped without a
collector in simple deployments.

Set the service name via `OTEL_SERVICE_NAME` env var (default `imgcache`).

### Instruments (use OTel Meter API)

| Instrument | Type | Description |
|---|---|---|
| `imgcache.store.total` | Counter | `result` attribute: `"created"` or `"duplicate"` |
| `imgcache.lookup.total` | Counter | `result` attribute: `"hit"` or `"miss"` |
| `imgcache.image_bytes` | Histogram | Raw byte size of each stored image |
| `imgcache.perceptual_hash.computed` | Counter | `result` attribute: `"ok"` or `"failed"` |
| `imgcache.similar_search.total` | Counter | Incremented on every similarity search |

Initialize the OTel SDK in the FastAPI lifespan. Use a `MeterProvider` with
both exporters registered. Shut down the provider cleanly on app shutdown (end
of lifespan).

---

## Python client package

Provide a pip-installable package in `client/` with a `ImgCacheClient` class
backed by `httpx`. Methods:

- `store(url, file_bytes, client_name, lookup_time, filename=None) -> dict` — POST multipart
- `get_bytes(content_hash) -> bytes` — GET raw image bytes
- `get_meta(content_hash) -> dict | None`
- `lookup(url) -> dict | None`
- `search(url_contains) -> list[dict]`
- `similar(perceptual_hash, max_hamming_distance=4) -> list[dict]`
- `delete(content_hash) -> None`
- `health() -> dict`
- Context manager support (`__enter__` / `__exit__`)

---

## Docker

### Dockerfile
- Base image: `python:3.11-slim`
- Install requirements, copy `app/`, run with `uvicorn` on port 8000.

### docker-compose.yml
- Single `imgcache` service, local storage only (`STORAGE_BACKEND=local`).
- Mount `./data:/data` as a **bind mount to a real host path** — not a named
  Docker volume — so files survive container rebuilds.
- No MinIO service in docker-compose (MinIO is only used in tests via
  testcontainer).

### rebuild.sh
Include a `rebuild.sh` script that runs `docker compose down`,
`docker compose up --build -d`, then tails logs.

---

## Tests

Use pytest. All tests must pass with `python -m pytest tests/` from the project
root.

### conftest.py
- Set `STORAGE_BACKEND`, `DATABASE_URL`, `LOCAL_STORAGE_PATH` env vars at
  **module level** (before any app imports) to prevent pydantic-settings from
  reading `.env` or system env during tests.
- `app` fixture: in-memory SQLite with `StaticPool`, temp dir for storage,
  patches the lazy engine/session singletons on `app.database`, overrides the
  storage singleton via `override_storage()`, cleans up after each test.
- `client` fixture: `TestClient(app)`.
- `minio_container` fixture: session-scoped `MinioContainer` from
  `testcontainers[minio]`. Skip automatically if Docker or testcontainers is
  unavailable.
- `s3_app` and `s3_client` fixtures mirroring the local ones but using the
  MinIO container.

### test_api.py
Cover: store new image (201), store duplicate (200), get bytes (correct
Content-Type header), get meta by hash, lookup by exact URL (hit + miss),
search by URL substring (matches with query params, empty list on no match,
search result contains no binary data field), delete (204 + subsequent 404),
health check.

### test_storage_local.py
Unit tests for `LocalStorage`: write/read round-trip, exists true/false, read
missing raises FileNotFoundError, delete removes file, delete is no-op when
missing, directory created on init, file named by hash.

### test_storage_s3.py
Integration tests via MinIO testcontainer (auto-skipped without Docker): store
+ retrieve, dedup, delete, search. Mirror test_api.py contract tests but run
against the S3 backend.

### test_perceptual.py
Unit tests for the perceptual hash utility: same image at two different
resolutions produces hamming distance ≤ 4, completely different images produce
hamming distance > 10, SVG/invalid bytes return None without raising.

### test_metrics.py
Verify `/metrics` endpoint is reachable and returns 200, and that each custom
OTel counter name appears in the output after triggering the relevant operation.

---

## Dependencies

### requirements.txt
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
pydantic-settings>=2.0.0
boto3>=1.34.0
Pillow>=10.0.0
imagehash>=4.3.1
opentelemetry-api>=1.24.0
opentelemetry-sdk>=1.24.0
opentelemetry-exporter-otlp-proto-grpc>=1.24.0
opentelemetry-exporter-prometheus>=0.45b0
opentelemetry-instrumentation-fastapi>=0.45b0
python-multipart>=0.0.9
```

### requirements-dev.txt
```
pytest>=8.0.0
httpx>=0.27.0
anyio[trio]>=4.0.0
testcontainers[minio]>=4.0.0
```

### client/setup.py
```
install_requires=["httpx>=0.27.0"]
```

---

## Project layout

```
imgcache/
├── app/
│   ├── main.py            FastAPI app, OTel SDK init in lifespan
│   ├── config.py          pydantic-settings
│   ├── database.py        lazy engine + session factory
│   ├── models.py          ImageEntry ORM model
│   ├── schemas.py         ImageEntryMeta pydantic model
│   ├── metrics.py         OTel meter, instruments, init_metrics()
│   ├── perceptual.py      compute_dhash(bytes) -> str | None
│   ├── routes/
│   │   └── images.py      all /images endpoints
│   └── storage/
│       ├── base.py
│       ├── local.py
│       └── s3.py
│       └── __init__.py    get_storage / override_storage / reset_storage
├── client/
│   ├── __init__.py
│   ├── imgcache_client.py
│   └── setup.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_storage_local.py
│   ├── test_storage_s3.py
│   ├── test_perceptual.py
│   └── test_metrics.py
├── docs/
│   ├── api.md
│   └── architecture.md
├── Dockerfile
├── docker-compose.yml
├── rebuild.sh
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```
