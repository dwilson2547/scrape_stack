# imgcache Architecture Overview

## System Purpose

imgcache is a content-addressed image caching service. Clients submit images alongside their source URL and retrieval metadata; the server deduplicates by content hash, stores the binary, and records rich metadata for later lookup, search, and perceptual similarity queries.

---

## Storage Abstraction

All binary storage is accessed through `BaseStorage` (`app/storage/base.py`), which defines four operations: `write`, `read`, `delete`, and `exists`. Two concrete backends are provided:

- **`LocalStorage`** (`app/storage/local.py`): stores each image as a file named by its content hash under a configurable directory (`LOCAL_STORAGE_PATH`).
- **`S3Storage`** (`app/storage/s3.py`): stores objects in an S3-compatible bucket (AWS S3 or MinIO). The bucket is auto-created on first use if it does not exist.

### Switching Backends

Set the `STORAGE_BACKEND` environment variable:

```env
STORAGE_BACKEND=local        # default
STORAGE_BACKEND=s3
```

For S3, also set:
```env
S3_BUCKET=imgcache
S3_ENDPOINT_URL=http://localhost:9000   # omit for real AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

---

## Lazy Initialisation Pattern

Both the database engine and the storage backend use module-level singletons with lazy initialisation:

- `app/database.py` — `get_engine()` creates the SQLAlchemy engine on first call and caches it in `_engine`.
- `app/storage/__init__.py` — `get_storage()` instantiates the configured backend on first call and caches it in `_storage`.

Test fixtures call `override_engine(engine)` and `override_storage(instance)` to inject in-memory / temporary alternatives before the application handles any requests, ensuring full isolation between test cases without modifying application code.

---

## Deduplication Flow

```
POST /images
  │
  ├─ Read file bytes
  ├─ Compute BLAKE2b-32 content hash
  │
  ├─ Query DB: does content_hash exist?
  │   ├─ YES → return 200 with existing metadata (no storage write)
  │   └─ NO  → continue
  │
  ├─ Detect content type (Pillow format detection, SVG sniffing)
  ├─ Extract image dimensions (Pillow)
  ├─ Compute perceptual dHash (imagehash)
  │
  ├─ INSERT ImageEntry into database
  ├─ Write bytes to storage backend (keyed by content hash)
  └─ Return 201 with metadata
```

The content hash is computed with `hashlib.blake2b(data, digest_size=32)`, producing a 64-character hex string. The database has a `UNIQUE` constraint on `content_hash`, so even under concurrent writes only one record is stored.

---

## Perceptual Hash Similarity

`app/perceptual.py` uses `imagehash.dhash()` (difference hash) from the `imagehash` library. The dHash algorithm:

1. Resizes the image to 9×8 pixels in greyscale.
2. For each row, compares each pixel to its right neighbour, producing 1 bit.
3. Concatenates all 64 bits to form a 64-bit integer, returned as a 16-character hex string.

dHash is robust to:
- Resizing / resolution changes (tested in `test_perceptual.py`)
- Minor colour adjustments
- JPEG compression artefacts

The `/images/similar` endpoint computes the **Hamming distance** (number of differing bits) between the query hash and every stored hash, returning entries within `max_hamming_distance` bits (default 4).

Non-image files (SVG, binary blobs) return `None` from `compute_dhash`, and those entries are excluded from similarity queries.

---

## OTel Metrics Pipeline

`app/metrics.py` sets up two metric export paths on startup:

```
MeterProvider
  ├─ PeriodicExportingMetricReader → OTLPMetricExporter (gRPC, configurable endpoint)
  └─ PrometheusMetricReader        → CollectorRegistry  → GET /metrics
```

A fresh `CollectorRegistry` is created per `init_metrics()` call, which prevents Prometheus duplicate-registration errors when the metrics module is re-initialised (e.g., in tests).

The `OTLPMetricExporter` pushes metrics to an OpenTelemetry Collector (default `http://localhost:4317`). If no collector is running the exporter silently fails in the background — the application continues serving traffic and Prometheus scraping still works.

### Instrumented Events

| Event | Metric | Labels |
|-------|--------|--------|
| Image stored | `imgcache.store.total` | `result=created\|duplicate` |
| URL lookup | `imgcache.lookup.total` | `result=hit\|miss` |
| Image bytes | `imgcache.image_bytes` | — |
| Perceptual hash | `imgcache.perceptual_hash.computed` | `result=ok\|failed` |
| Similarity search | `imgcache.similar_search.total` | — |

Metrics instruments are `None` until `init_metrics()` runs (during FastAPI lifespan startup). All increment calls are guarded with `if m.xxx_counter:` to allow safe use before/during testing.

---

## Database

SQLAlchemy 2.x with `DeclarativeBase`. A single table `image_entries` holds all metadata. The `content_hash` column has a `UNIQUE` constraint and index. The `url` column is indexed for fast lookup and search.

SQLite is used by default (`DATABASE_URL=sqlite:///./imgcache.db`). Any SQLAlchemy-compatible database (PostgreSQL, MySQL) can be substituted via the `DATABASE_URL` environment variable.

---

## Configuration

All settings are managed by `pydantic-settings` (`app/config.py`). Values can be overridden with environment variables or a `.env` file. See `.env.example` for the full list of supported variables.
