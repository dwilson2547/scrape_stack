# scrape_stack

Unified docker-compose stack that brings up the full web scraping service suite in one command.

## Services

| Service | Host Port | Description |
|---|---|---|
| webcache | 8000 | HTTP response cache |
| imgcache | 8010 | Image dedup cache |
| filecache | 8030 | Generic file cache |
| vidcache | 8020 | Video dedup cache |
| request-auth-server | 9000 (gRPC), 9003 (HTTP) | Rate-limit permit server |
| request-auth-api | 9001 | Management REST API |
| request-auth-ui | 9002 | Management UI |
| postgres | 5433 (host) | Shared Postgres 16 (mapped to 5433 to avoid host conflicts) |
| browserless | 4000 | Headless Chrome for webcache `/render` |

> **Note:** These ports match the canonical per-service ports. Stop any individually-running service stacks before starting scrape_stack.

## Setup

Copy the example env file and set a strong Postgres password:

```bash
cp .env.example .env
# edit .env and set POSTGRES_PASSWORD
```

## Commands

**Start**
```bash
docker compose up -d
```

**Stop**
```bash
docker compose down
```

**Restart a service**
```bash
docker compose restart <service>
```

**Rebuild and restart**
```bash
docker compose up -d --build
```

**Logs**
```bash
docker compose logs -f <service>
```

## Data

All persistent data is stored under `./data/` (created automatically on first start):

- `./data/postgres` — Postgres data directory
- `./data/webcache` — webcache local file storage
- `./data/imgcache` — imgcache local file storage
- `./data/filecache` — filecache local file storage
- `./data/vidcache` — vidcache local file storage
- `./data/request-auth` — request-auth SQLite database

> The request-auth server uses SQLite (shared between the Go server and Python API via a volume mount). The four cache services all connect to the shared Postgres instance.

## OTEL

This stack does not include an OTEL collector — deploy the otel stack separately and point services at it via `OTEL_EXPORTER_OTLP_ENDPOINT` in `.env` if needed.
