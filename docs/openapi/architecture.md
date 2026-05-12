# Scraper Service Architecture

```mermaid
flowchart TD
    EXT(["External Sites"])

    RA["request_authorization
    ─────────────────────
    Domain permit queue
    Blocking per-domain concurrency"]

    subgraph caches ["Cache Services"]
        WC["webcache  :8000
        ────────────────
        text / HTML
        client-upload only"]

        IC["imgcache  :8010
        ────────────────
        images + perceptual hash
        client-upload only"]

        VC["vidcache  :8020
        ────────────────
        video + phash
        server-side download"]

        FC["filecache  :8030
        ────────────────
        arbitrary files
        client upload · server download"]
    end

    SC(["Scrapers
    bot_scraper_lib"])

    subgraph storage ["Storage  (per service)"]
        DB[("Index DB
        SQLite → Postgres")]
        FS[("Content Store
        Local FS / S3")]
    end

    %% ── Client-side upload (webcache, imgcache)
    %% Scraper owns the HTTP fetch; cache receives bytes only
    SC -->|"acquire permit  (domain)"| RA
    RA -.->|"permit granted"| SC
    SC -->|"HTTP GET"| EXT
    SC -.->|"release + HTTP status"| RA
    SC -->|"POST store
    bucket / prefix / content"| WC
    SC -->|"POST store
    bucket / prefix / image"| IC

    %% ── Server-side download (vidcache, filecache /download)
    %% Scraper sends a URL; cache service owns the HTTP fetch
    SC -->|"POST /download
    url · bucket · prefix"| VC
    SC -->|"POST /download
    url · bucket · prefix"| FC
    VC & FC -->|"acquire permit  (domain)"| RA
    RA -.->|"permit granted"| VC & FC
    VC & FC -->|"HTTP GET"| EXT
    VC & FC -.->|"release + HTTP status"| RA

    %% ── Two-phase client upload (filecache only)
    SC -->|"POST /upload/init  (+ optional content_hash)
    POST /upload/{id}  (stream bytes)"| FC

    %% ── Reads (all caches)
    SC -.->|"lookup · resolve · meta · stream"| WC & IC & VC & FC

    %% ── Storage writes (all caches)
    WC & IC & VC & FC ==> DB
    WC & IC & VC & FC ==> FS
```

## Upload patterns

**Client-side upload** (webcache, imgcache) — the scraper acquires a permit from
`request_authorization`, performs the HTTP fetch itself, releases the permit, then
pushes the bytes to the cache service along with a pre-computed BLAKE3 `content_hash`.
The server deduplicates on the hash before writing — if the hash is already stored the
content body is ignored and `status: duplicate` is returned immediately.

**Server-side download** (vidcache, filecache `/download`) — the scraper hands a URL
to the cache service. The cache acquires the permit, performs the fetch, releases the
permit, stores the content, and returns the metadata record. The scraper never touches
the bytes.

**Two-phase client upload** (filecache/vidcache) — the scraper calls `POST /upload/init`
with a pre-computed `content_hash`. If the hash is already stored the server returns
`status: fresh` or `cached` and no bytes are transferred. Only if `status: pending` does
the scraper stream bytes to `POST /upload/{id}`.

## Content hash standard

All clients compute a BLAKE3 hash of the content before any upload call. This is the
universal dedup key across all services:

| Service | Hash sent at | Required? | Short-circuit |
| --- | --- | --- | --- |
| webcache | `POST /cache` body | yes | server ignores body if hash known |
| imgcache | `POST /cache` body | yes | server ignores body if hash known |
| filecache | `POST /upload/init` | expected | returns `fresh`/`cached`, skips upload |
| vidcache | `POST /upload/init` | expected | returns `fresh`/`cached`, skips upload |

## Storage

Each cache service maintains its own SQLite index today. The shared Postgres schema
(`cache_entries`, `url_map`, service-specific `*_meta` tables) is the migration target
that will enable the cache browser.
