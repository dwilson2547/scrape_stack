# Request Authorization Service — Design Spec
**Date:** 2026-05-07
**Status:** Approved

---

## Overview

A centralized rate-limiting permit service for the web scraper ecosystem. Scrapers request a permit before making an HTTP request; the server enforces per-domain rate limits, backoff, and robots.txt constraints. Communication uses gRPC bidirectional streaming for minimum latency.

---

## Architecture

Four components sharing two data boundaries:

```
Python Scrapers (dwilson-request-auth-client)
        ↕ gRPC bidirectional stream :9000
Go gRPC Server ←→ SQLite DB
        ↕ HTTP /status :9003
FastAPI Management API :9001 ←→ SQLite DB
        ↕ REST
React UI :9002

OTel export → OTLP gRPC :4317 (external stack, configurable via OTEL_EXPORTER_OTLP_ENDPOINT)
```

**Ports:**
- `9000` — gRPC permit stream
- `9001` — FastAPI management API
- `9002` — React UI
- `9003` — gRPC server HTTP `/status` (live pool state for UI)

The gRPC server and FastAPI both access SQLite directly. The API is management-only; it is never in the hot path for permit issuance.

The gRPC server caches domain/bucket/global config in-memory and reloads from SQLite at a configurable interval (default 30s). This keeps SQLite off the permit grant hot path. Config changes made via the API take effect within one reload interval.

---

## gRPC Protocol

Single bidirectional stream per client connection. All domains multiplexed over it.

### permit.proto

```protobuf
service PermitService {
  rpc PermitStream(stream ClientMessage) returns (stream ServerMessage);
}

message ClientMessage {
  oneof payload {
    PermitRequest request = 1;
    PermitReturn  ret     = 2;
  }
}

message ServerMessage {
  oneof payload {
    PermitGrant  grant = 1;
    ServerError  error = 2;
  }
}

message PermitRequest {
  string domain = 1;
  int64  req_id = 2;  // client-side incrementing counter, echoed in grant
}

message PermitGrant {
  string permit_id = 1;
  int64  req_id    = 2;
  int32  ttl_ms    = 3;  // advisory — server's expected hold time
}

message PermitReturn {
  string permit_id    = 1;
  int32  status_code  = 2;  // HTTP status scraper received; 0 = unknown/crash
}

message ServerError {
  int64  req_id  = 1;
  string message = 2;
}
```

### Stream lifecycle

**Happy path:**
1. Client opens stream on startup (reconnects automatically on drop)
2. Client sends `PermitRequest{domain, req_id}`
3. Server queues request in domain's permit pool
4. Server sends `PermitGrant{permit_id, req_id}` when a slot is available
5. Client does HTTP work
6. Client sends `PermitReturn{permit_id, status_code}`
7. Server records status code, applies backoff, issues next grant from queue

**429 received:**
- Client returns permit with `status_code: 429`
- Server records 429 metric for domain (OTel counter)
- Server multiplies current backoff by `backoff_multiplier`
- Backoff decays after `recovery_threshold` consecutive 2xx responses

**Client disconnect / crash:**
- Server detects stream EOF
- All permits held by that client are implicitly returned with `status_code: 0`
- Backoff applied before re-issuing to next waiter

---

## Permit Pool & Backoff

### Per-domain pool

Each domain has an independent permit pool:
- **Pool slots** — `pool_size` concurrent permits can be held simultaneously
- **Wait queue** — FIFO queue of pending `PermitRequest`s
- Slot states: `FREE` → `HELD` (grant issued) → `BACKOFF` (return received, timer running) → `FREE`

### Backoff config (per domain or bucket, nullable → inherits)

| Field | Default | Description |
|---|---|---|
| `base_delay_ms` | 1000 | Normal delay between requests |
| `backoff_multiplier` | 3.0 | Factor applied on 429 |
| `max_delay_ms` | 60000 | Ceiling for backoff growth |
| `recovery_threshold` | 10 | Consecutive 2xx before backoff decays to base |
| `pool_size` | 1 | Concurrent permits issued at once |

Backoff state (`current_delay_ms`, `consecutive_2xx` count) is **in-memory only** on the gRPC server — not persisted. Resets to `base_delay_ms` on server restart.

### Config priority (highest → lowest)

1. Domain-specific override
2. Bucket config (if domain belongs to a bucket)
3. robots.txt `Crawl-delay` directive
4. Global default (`global_config` table)

---

## Domain Buckets

Named groups of domains sharing one rate-limit config. A domain belongs to at most one bucket. Domain-level overrides always win over bucket config.

**Example:**
```
cdn-bucket:       cloudfront.net, fastly.net, akamai.com
                  pool_size:10, base_delay_ms:0, max_delay_ms:1000

junkyard-bucket:  lkq.com, pick-n-pull.com, row52.com
                  pool_size:1, base_delay_ms:2000
```

---

## robots.txt Caching

**Unknown domain (no DB entry):** Server creates an in-memory pool using global defaults, inserts a `domains` row, and triggers an async robots.txt fetch. Permits are issued immediately using global defaults while the fetch is in flight; config is updated once the fetch completes.

- Fetched on first permit request for an unknown domain
- Stored in DB with `fetched_at`, `expires_at` (configurable TTL, default 24h)
- If expired at request time: server re-fetches before issuing permit
- If fetch fails: record `checked_at`, retry at configurable interval (default 24h)
- `Crawl-delay` parsed and used as `base_delay_ms` at priority level 3

### Overrides

- User sets override via API/UI → `is_overridden=true`, `override_delay_ms` set, `original_crawl_delay_ms` preserved
- UI shows amber "overridden" badge and a Revert button
- Revert clears `is_overridden`, restores `crawl_delay_ms` from `original_crawl_delay_ms`

---

## Database Schema

### `buckets`
```sql
id, name, pool_size, base_delay_ms, backoff_multiplier,
max_delay_ms, recovery_threshold, created_at, updated_at
```

### `domains`
```sql
id, name, bucket_id (FK nullable),
pool_size (nullable), base_delay_ms (nullable),
backoff_multiplier (nullable), max_delay_ms (nullable),
recovery_threshold (nullable),
created_at, updated_at
```
Nullable rate fields mean "fall through to next priority level."

### `robots_txt_cache`
```sql
id, domain (unique), raw_content, crawl_delay_ms,
fetched_at, expires_at, checked_at,
is_overridden, override_delay_ms, original_crawl_delay_ms,
created_at, updated_at
```

### `global_config`
```sql
key (PK), value, updated_at
```
Keys: `default_pool_size`, `default_base_delay_ms`, `default_backoff_multiplier`, `default_max_delay_ms`, `default_recovery_threshold`, `robots_txt_ttl_hours`, `robots_txt_retry_hours`.

---

## OTel Metrics

All metrics emitted via OTel Go SDK, exported via OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT` (default `localhost:4317`).

| Metric | Type | Labels |
|---|---|---|
| `permit.wait_duration_ms` | Histogram | `domain` |
| `permit.hold_duration_ms` | Histogram | `domain` |
| `permit.active` | Gauge | `domain` |
| `permit.queued` | Gauge | `domain` |
| `permit.issued_total` | Counter | `domain` |
| `permit.backoff_duration_ms` | Histogram | `domain` |
| `response.status_total` | Counter | `domain`, `status_code` |
| `robots_txt.fetch_total` | Counter | `domain`, `result` (ok/fail/notfound) |

The `/status` endpoint on `:9003` returns a JSON snapshot of current in-memory pool state (active, queued, current_delay_ms, 429 counts per domain). Used by the UI via the management API proxy — separate from the OTel pipeline.

---

## Management API Endpoints

Base path: `/api`

```
GET  /domains                       list all domains
POST /domains                       create domain
GET  /domains/{id}                  get domain
PATCH /domains/{id}                 update domain config
DEL  /domains/{id}                  delete domain

GET  /buckets                       list all buckets
POST /buckets                       create bucket
GET  /buckets/{id}                  get bucket + members
PATCH /buckets/{id}                 update bucket config
DEL  /buckets/{id}                  delete bucket
POST /buckets/{id}/domains          add domain to bucket
DEL  /buckets/{id}/domains/{did}    remove domain from bucket

GET  /robots/{domain}               get cache entry + override status
POST /robots/{domain}/override      set manual delay override
POST /robots/{domain}/revert        restore robots.txt value
POST /robots/{domain}/refresh       force re-fetch

GET  /config                        get global defaults
PATCH /config                       update global defaults

GET  /status                        proxy to gRPC server :9003/status
```

---

## React UI

Four pages accessed via top nav:

**Dashboard** — stat strip (active permits, queued, 429s/1h, domain count, permits/min) + live domain status table (domain, bucket, active, queued, current delay, 429 count, status badge). Polls `/api/status` on a short interval.

**Domains** — searchable list, add/edit domain config, inline bucket assignment.

**Buckets** — bucket cards with member chip list, "+ Add domain" inline, rate config editing.

**robots.txt** — per-domain cards showing current crawl-delay, expiry, override status. Override badge (amber), Revert button, Force Refresh button, "none found" state with retry countdown.

Components are designed to be reusable for a future unified scraper command dashboard.

---

## Python Client

Package: `dwilson-request-auth-client` (PyPI)
Module: `request_auth_client`

```python
from request_auth_client import RequestAuthClient

client = RequestAuthClient("localhost:9000")

# Explicit release
permit = client.acquire("rockauto.com")  # blocks until granted
try:
    response = requests.get(url)
    permit.release(response.status_code)
except Exception:
    permit.release(0)

# Context manager (preferred)
with client.acquire("rockauto.com") as permit:
    response = requests.get(url)
    permit.set_status(response.status_code)
# auto-releases on exit; status defaults to 0 if not set
```

Stream lifecycle (connect, reconnect, request ID tracking) is fully internal. Sync-first; asyncio conversion is straightforward later.

---

## Folder Structure

```
request_authorization/
├── server/
│   ├── app/
│   │   ├── main.go
│   │   ├── proto/          # .proto + generated Go code
│   │   ├── pool/           # permit pool, backoff engine
│   │   ├── robots/         # robots.txt fetcher + cache reader
│   │   ├── metrics/        # OTel setup
│   │   └── db/             # SQLite reader (config + robots cache)
│   ├── Dockerfile
│   └── readme.md
├── client/
│   ├── request_auth_client.py
│   ├── setup.py
│   └── readme.md
├── api/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   └── routes/
│   ├── Dockerfile
│   └── requirements.txt
├── ui/
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── proto/
│   └── permit.proto
├── docker-compose.yaml
└── readme.md
```

---

## Docker Compose

Services and ports:

| Service | Port | Notes |
|---|---|---|
| `server` | 9000 (gRPC), 9003 (HTTP) | Go, built from `server/Dockerfile` |
| `api` | 9001 | FastAPI, SQLite volume-mounted |
| `ui` | 9002 | React, proxies `/api` to `api:9001` |

SQLite DB file mounted as a shared volume accessible to both `server` and `api`.
`OTEL_EXPORTER_OTLP_ENDPOINT` defaults to `http://localhost:4317`; override to point at running OTel stack.

---

## Stretch Goal (not in scope)

Auto-tune permit rate per domain: gradually ramp up request rate, halve on 429, stabilize slightly below the 429 threshold. Deferred — debugging a feedback control loop across distributed scrapers is non-trivial.
