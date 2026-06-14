# filecache

A content-addressed file caching service for arbitrary binary files — PDFs, ZIPs, HTML, images, video, and more. Files are stored once (deduplicated by BLAKE3 hash) regardless of how many source URLs point to them.

Part of the scraper cache stack alongside [webcache](../webcache), [imgcache](../imgcache), and [vidcache](../vidcache).

Default port: **8030**

---

## Overview

- **Content addressing** — the BLAKE3 hash of a file's bytes is its primary key and its on-disk filename. The same bytes stored under different URLs are stored exactly once.
- **URL map** — a `url_map` table links many source URLs to a single file hash, enabling fast URL-based lookups without re-hashing.
- **Two ingestion paths**
  - *Client push* — the caller downloads the file and streams it to `/upload/{upload_id}` (two-phase protocol).
  - *Server pull* — `POST /download` instructs the service to fetch the URL itself, using the `request_auth` rate-limiter.
- **Pluggable storage** — local filesystem or S3/MinIO.
- **On-disk layout** — files are sharded two levels deep to avoid inode limits:
  ```
  {root}/{bucket}/{prefix}/{hash[0:2]}/{hash[2:4]}/{hash}{ext}
  ```

---

## Getting Started (local)

**Prerequisites:** Python 3.11+.

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit the default config
cp config.yaml my-config.yaml
# Edit my-config.yaml as needed (see Configuration below)

# Run
python main.py --config my-config.yaml

# Verify
curl http://localhost:8030/health
# {"status": "ok"}
```

---

## Docker

Build from the `filecache/` repo root:

```bash
docker build -f Dockerfile -t filecache .
docker run -p 8030:8030 -v /data/filecache:/data/filecache filecache
```

### Docker Compose example

```yaml
services:
  filecache:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8030:8030"
    volumes:
      - /data/filecache:/data/filecache
    environment:
      DATABASE_URL: ""    # leave blank to use SQLite at index.db_path
```

---

## Configuration

### `config.yaml`

```yaml
storage:
  backend: local          # "local" or "s3"
  local:
    root: /data/filecache
  # s3:
  #   endpoint: http://minio:9000
  #   access_key: minioadmin
  #   secret_key: minioadmin
  #   region: us-east-1
  #   bucket: filecache
  #   multipart_threshold_mb: 100
  #   multipart_part_size_mb: 64

index:
  db_path: /data/filecache/index.db
  # database_url: postgresql://user:pass@host/db   # overrides db_path

request_auth:
  address: localhost:9000
  enabled: true

ingest:
  temp_dir: /tmp/filecache
  chunk_size_mb: 1

server:
  host: 0.0.0.0
  port: 8030
```

### Full config reference

| Section | Key | Default | Description |
|---|---|---|---|
| `storage` | `backend` | `local` | Storage backend: `local` or `s3` |
| `storage.local` | `root` | `/data/filecache` | Root directory for local storage |
| `storage.s3` | `endpoint` | _(AWS)_ | S3/MinIO endpoint URL |
| `storage.s3` | `access_key` | | S3 access key |
| `storage.s3` | `secret_key` | | S3 secret key |
| `storage.s3` | `region` | `us-east-1` | S3 region |
| `storage.s3` | `bucket` | `filecache` | S3 bucket name |
| `storage.s3` | `multipart_threshold_mb` | `100` | File size above which multipart upload is used |
| `storage.s3` | `multipart_part_size_mb` | `64` | Multipart part size |
| `index` | `db_path` | `/data/filecache/index.db` | SQLite database path |
| `index` | `database_url` | | Full DB connection string (PostgreSQL). Overrides `db_path`. |
| `request_auth` | `address` | `localhost:9000` | Address of the `request_auth` service |
| `request_auth` | `enabled` | `true` | Enable per-domain rate-limit permits on server-side downloads |
| `ingest` | `temp_dir` | `/tmp/filecache` | Temp directory for in-flight server-side downloads |
| `ingest` | `chunk_size_mb` | `1` | HTTP read chunk size for server-side downloads |
| `server` | `host` | `0.0.0.0` | Uvicorn bind host |
| `server` | `port` | `8030` | Uvicorn bind port |

### Environment variables

| Variable | Effect |
|---|---|
| `DATABASE_URL` | Overrides `index.database_url` (highest priority) |
| `OTEL_SERVICE_NAME` | Service name reported in metrics (default: `filecache`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | When set, enables OTLP metric export to this endpoint |

---

## Storage Backends

| | Local | S3 / MinIO |
|---|---|---|
| **Config section** | `storage.local` | `storage.s3` |
| **Byte-range reads** | Yes (HTTP 206) | Yes (Range GET) |
| **Auto-create bucket** | N/A | Yes |
| **Multipart upload** | N/A | Yes (configurable threshold) |
| **Use case** | Single-host deployments | Distributed / production |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check → `{"status": "ok"}` |
| `GET` | `/metrics` | Prometheus metrics (text/plain) |
| `POST` | `/upload/init` | **Phase 1** of two-phase upload. Returns `fresh` (already cached by hash), `cached` (URL already seen), or `pending` + `upload_id`. |
| `POST` | `/upload/{upload_id}` | **Phase 2**: stream raw file bytes. Returns `{"status": "new"\|"duplicate", "hash": "..."}`. |
| `POST` | `/download` | Server-side pull: the service fetches the URL, using `request_auth` for rate limiting. |
| `GET` | `/cache/{hash}` | Stream file bytes. Supports `Range:` header (HTTP 206), `ETag`, `Cache-Control: immutable`. |
| `GET` | `/cache/meta/{hash}` | File metadata + all known source URLs for this hash. |
| `GET` | `/cache/resolve` | `?url=` → resolve a URL to its hash. |
| `GET` | `/cache/lookup` | `?url=&max_age=&version=` — URL lookup with optional freshness check or version pin. |
| `GET` | `/cache/search` | `?url_contains=&bucket=` — substring search across stored URLs in a bucket. |
| `DELETE` | `/cache/{hash}` | Delete a file from storage and the index. |
| `GET` | `/browse` | Paginated, filterable file listing (bucket, prefix, client_name, date range, URL substring, cursor). |
| `GET` | `/browse/buckets` | List all distinct bucket names. |
| `GET` | `/browse/prefixes` | `?bucket=` — list all prefixes within a bucket. |

### Two-phase upload (`/upload/init` → `/upload/{upload_id}`)

`POST /upload/init` body:

```json
{
  "url": "https://example.com/report.pdf",
  "bucket": "documents",
  "filename": "report.pdf",
  "hash": "a3f4..."          // optional BLAKE3 hash — enables "fresh" fast-path
}
```

| `status` in response | Meaning |
|---|---|
| `fresh` | Hash already in store — skip upload entirely |
| `cached` | URL was seen before and file exists — skip upload |
| `pending` | File not found — proceed to `POST /upload/{upload_id}` |

---

## Python Client SDK

Install from the `client/` directory:

```bash
pip install -e filecache/client/
```

```python
from filecache_client import FileCacheClient

client = FileCacheClient("http://localhost:8030")

# Convenience method: client fetches the URL and streams bytes to the cache
result = client.ingest_from_url(
    url="https://example.com/report.pdf",
    bucket="documents",
    filename="report.pdf",
)
print(result["hash"])    # BLAKE3 content hash (64 hex chars)
print(result["status"])  # "new" | "duplicate"

# Drive the two phases manually
init = client.upload_init("https://example.com/report.pdf", bucket="documents", filename="report.pdf")
if init["status"] == "pending":
    with open("local.pdf", "rb") as f:
        result = client.upload_stream(init["upload_id"], f)

# Ask the server to download the file (uses request_auth internally)
result = client.server_download(
    url="https://example.com/protected.zip",
    bucket="archives",
    filename="protected.zip",
    cookies={"session": "abc"},
)

# Lookup by URL with a freshness constraint (max_age in seconds)
entry = client.lookup("https://example.com/report.pdf", max_age=86400)

# Stream file bytes to disk
with client.stream_file(entry["hash"]) as chunks:
    with open("local_copy.pdf", "wb") as f:
        for chunk in chunks:
            f.write(chunk)

client.close()  # or use as a context manager: with FileCacheClient(...) as client:
```

---

## Metrics & Observability

Prometheus metrics are exposed at `GET /metrics`.

| Instrument | Type | Description |
|---|---|---|
| `filecache.upload_init.total` | Counter | Two-phase upload init requests |
| `filecache.ingest.total` | Counter | Completed file ingest operations |
| `filecache.download.total` | Counter | Server-side download operations |
| `filecache.lookup.total` | Counter | File retrieval requests |
| `filecache.file_bytes` | Histogram | Size in bytes of newly stored files |

### OTLP export

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to push metrics to an OpenTelemetry collector:

```bash
OTEL_SERVICE_NAME=filecache \
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
python main.py --config config.yaml
```

A Grafana dashboard definition is provided in [`grafana-dashboard.json`](grafana-dashboard.json).
