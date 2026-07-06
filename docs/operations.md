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

## Optional Monitoring Stack (OTEL + Prometheus + Grafana)

You can keep monitoring optional by using the side compose file at the repo root:

**Start app + monitoring**
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

**Start monitoring only**
```bash
docker compose -f docker-compose.monitoring.yml up -d
```

**Stop monitoring**
```bash
docker compose -f docker-compose.monitoring.yml down
```

| Service | Host Port |
|---|---|
| OTEL Collector (gRPC) | 4317 |
| OTEL Collector (HTTP) | 4318 |
| Collector Prometheus endpoint | 8889 |
| Prometheus UI | 9090 |
| Grafana UI | 3000 |

Grafana is auto-provisioned with Prometheus and auto-loads dashboards from:
- `services/webcache/grafana-dashboard.json`
- `services/imgcache/grafana-dashboard.json`
- `services/filecache/grafana-dashboard.json`
- `services/vidcache/grafana-dashboard.json`
- `services/request_authorization/grafana-dashboard.json`
- `tools/http-test-service/grafana-dashboard.json`

## Helm Chart (separate from `k8s/`)

A standalone Helm chart is available under `helm/scrape-stack/`.  
The existing `k8s/` manifests are left as-is.

**Render templates**
```bash
helm template scrape-stack ./helm/scrape-stack -n scrape-stack
```

**Install**
```bash
helm upgrade --install scrape-stack ./helm/scrape-stack -n scrape-stack --create-namespace
```

**Customize**
```bash
helm upgrade --install scrape-stack ./helm/scrape-stack -n scrape-stack --create-namespace -f my-values.yaml
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

Use `docker-compose.monitoring.yml` to run the bundled local OTEL monitoring stack when needed.

