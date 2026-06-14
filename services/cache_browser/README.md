# Cache Browser

Centralized browser UI for the scrape stack's four cache services: webcache, imgcache, filecache, and vidcache.

## Services

| Service | Port | Description |
|---------|------|-------------|
| `cache-browser-api` | 8040 | FastAPI aggregator — proxies browse/search to each cache |
| `cache-browser-ui` | 8041 | React SPA — the browser interface |

Both services are defined in `scrape_stack/docker-compose.yml` and run on `stack-net`.

## Architecture

```
browser → nginx (port 8041)
           ├── /api/       → cache-browser-api:8040
           ├── /proxy/web/ → webcache:8000
           ├── /proxy/image/ → imgcache:8010
           ├── /proxy/file/  → filecache:8030
           └── /proxy/video/ → vidcache:8020
```

The API service is a thin proxy — no database, no business logic. It forwards browse/search requests to the appropriate upstream cache and aggregates results for global search.

## Features

- **Bucket/prefix navigation** — sidebar tree matching the storage hierarchy used across all caches
- **Per-cache browsing** with cursor-based infinite scroll (keyset pagination, no offset)
- **Global search** — fans out to all four caches concurrently, handles partial failures gracefully
- **Filters** — date range, client name (scrape job), full-text URL search
- **Webcache viewer** — expandable HTML source with keyword highlighting
- **Image grid** — adjustable 2–8 column grid, lazy loading, download overlay
- **Video grid** — adjustable grid, IntersectionObserver autoplay, max 4 simultaneous, fullscreen
- **File list** — download links with filename, MIME type, and size

## Directory structure

```
cache_browser/
├── api/                    # FastAPI proxy/aggregator (port 8040)
│   ├── main.py
│   ├── config.py
│   ├── clients.py
│   ├── routers/
│   │   ├── browse.py       # /api/browse/{cache_type}[/buckets|/prefixes]
│   │   └── search.py       # /api/search (cross-cache)
│   ├── Dockerfile
│   └── requirements.txt
└── ui/                     # React 18 + TypeScript + Tailwind SPA (port 8041)
    ├── nginx.conf
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── api/            # fetch helpers + TanStack Query hooks
        ├── store/          # Zustand filter/UI state (persisted)
        ├── hooks/
        └── components/
            ├── Sidebar.tsx
            ├── FilterBar.tsx
            ├── BrowsePane.tsx
            ├── WebList.tsx / WebItem.tsx
            ├── ImageGrid.tsx / ImageItem.tsx
            ├── VideoGrid.tsx / VideoItem.tsx
            └── FileList.tsx / FileItem.tsx
```

## Running

Start the full stack from `scrape_stack/`:

```bash
docker compose up -d
```

Open the browser at `http://localhost:8041`.

## Prerequisites

The browse and search endpoints depend on `/browse` routes added to each cache service:
- `webcache` — `GET /browse`, `/browse/buckets`, `/browse/prefixes`
- `imgcache` — same
- `filecache` — same
- `vidcache` — same

These were added alongside this service. The `filecache` and `vidcache` models also received a `client_name` column (idempotent migration runs on startup).
