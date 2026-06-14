# rate-limit-testbed

A configurable HTTP service that simulates rate limiting, server errors, and latency, with full OpenTelemetry metrics export. Use it to validate retry/backoff logic in HTTP clients.

## Quick Start

```bash
docker compose up --build -d
```

This starts the `testbed` container on port **9004**. It expects an OTLP gRPC collector at `host.docker.internal:4317` (configurable via `config.yaml`). Run Prometheus and Grafana separately, or point any OTLP-compatible collector at the testbed.

## Routes

Three route modes are available, all configured in `config.yaml`:

### Probabilistic

Rejects requests randomly at a fixed rate.

| Method | Path            | Reject rate | Retry-After | Notes                               |
|--------|-----------------|-------------|-------------|-------------------------------------|
| GET    | `/api/resource` | 40%         | 2s          | Baseline backoff test               |
| GET    | `/api/fast`     | 5%          | 1s          | Mostly healthy — avoid over-backoff |
| GET    | `/api/slow`     | 70%         | 5s (HTTP date) | Hostile — tests Retry-After parsing |
| POST   | `/api/submit`   | 50%         | 3s          | Non-idempotent retry scenarios      |

### Windowed

Accepts N requests per time window then rejects the rest. Emits `X-RateLimit-Limit/Remaining/Reset` headers.

| Method | Path            | Limit         | Retry-After |
|--------|-----------------|---------------|-------------|
| GET    | `/api/windowed` | 10 req / 30s  | 30s         |

### Weighted distribution

Returns a configurable mix of status codes.

| Method | Path                    | Distribution              | Notes          |
|--------|-------------------------|---------------------------|----------------|
| GET    | `/api/scenario/mixed`   | 60% 200, 30% 429, 10% 503 | Wildcard path  |
| GET    | `/api/scenario/forbidden` | 70% 200, 30% 403         | Wildcard path  |

Wildcard routes also match any sub-path, e.g. `/api/scenario/mixed/foo/bar`.

### Built-in endpoints

| Path                         | Notes                                              |
|------------------------------|----------------------------------------------------|
| `GET  /healthz`              | Liveness check                                     |
| `GET  /_config`              | Dump running route config as JSON                  |
| `POST /_reset_windows`       | Reset all windowed counters (useful between tests) |
| `GET  /probe/<code>[/<path>]`| Always return the given HTTP status code           |
| `GET  /robots.txt`           | Served from `config.yaml`                          |

## Configuration

Edit `config.yaml` to add, remove, or tune routes. Changes take effect on restart.

**Probabilistic knobs:**
- `reject_rate` (0.0–1.0): probability of returning the reject status
- `reject_status` (default 429): status code to return on rejection
- `retry_after` (int|null): value of the `Retry-After` header; omit to suppress
- `retry_after_format`: `"seconds"` (default) or `"http_date"`
- `latency_ms` / `jitter_ms`: simulate real-world response time

**Windowed knobs:**
- `window_max`: number of requests to allow per window
- `window_seconds`: window duration
- `rate_limit_headers: true`: emit `X-RateLimit-*` headers

**Distribution knobs:**
- `status_distribution`: list of `{status, weight}` entries (weights are relative)
- `wildcard: true`: register the route as a prefix match

## Metrics (OTel → Prometheus)

| Metric                                    | Type      | Labels                                          |
|-------------------------------------------|-----------|-------------------------------------------------|
| `http_server_requests_total`              | Counter   | `http_route`, `http_method`                     |
| `http_server_rejected_total`              | Counter   | `http_route`, `http_method`                     |
| `http_server_accepted_total`              | Counter   | `http_route`, `http_method`                     |
| `http_server_duration_ms_milliseconds`    | Histogram | `http_route`, `http_method`, `http_status_code` |

The OTel SDK appends the unit suffix, so the Prometheus bucket metric is `http_server_duration_ms_milliseconds_bucket`.

PromQL examples:

```promql
# Overall rejection rate
rate(http_server_rejected_total[1m]) / rate(http_server_requests_total[1m])

# Per-route rejection rate
rate(http_server_rejected_total{http_route="/api/slow"}[1m])
  / rate(http_server_requests_total{http_route="/api/slow"}[1m])

# P99 latency by route
histogram_quantile(0.99,
  sum(rate(http_server_duration_ms_milliseconds_bucket[1m])) by (le, http_route)
)
```

## Load Generators

### Simple load generator (`load_gen.py`)

Quick smoke tests against all or a subset of routes:

```bash
pip install httpx
python load_gen.py                          # 10 rps, 60s, all routes
python load_gen.py --rps 50 --duration 30
python load_gen.py --routes /api/slow
```

Prints a live scoreboard of request counts and observed rejection rates.

### Phase-driven perf test (`perf_test/perf_test.py`)

Long-form load generator with configurable phases. Routes are discovered from `/_config` at startup.

```bash
python perf_test/perf_test.py                             # phases from perf_phases.yaml
python perf_test/perf_test.py --cycle                     # repeat all phases indefinitely
python perf_test/perf_test.py --config my.yaml            # alternate phase config
python perf_test/perf_test.py --base-url http://host:9004
```

Phases are defined in `perf_test/perf_phases.yaml`:

```yaml
phases:
  - name: warmup
    rps: 5
    duration_seconds: 60
  - name: normal
    rps: 20
    duration_seconds: 120
  - name: heavy
    rps: 60
    duration_seconds: 120
  - name: soak
    rps: 30
    hold: true    # runs until Ctrl+C / SIGTERM
```

Each phase can target a subset of routes via the `routes:` list. The last phase (or any phase with `hold: true`) runs indefinitely.

## Grafana Dashboard

`grafana-dashboard.json` is a ready-to-import Grafana 10+ dashboard. Import it via **Dashboards → Import → Upload JSON**.

Panels:

| Panel | Type | What it shows |
|---|---|---|
| Requests / sec | Stat | Global inbound rate |
| Rejections / sec | Stat | Global rejection rate |
| Rejection % | Stat | Global rejection percentage |
| P95 Latency | Stat | Global P95 across all routes |
| Request Rate by Route | Time series | Per-route request rate over time |
| Rejection Rate by Route | Time series | Per-route rejection rate over time |
| Rejection % by Route | Time series | Per-route rejection percentage over time |
| Request Rate by Status Code | Time series | Request rate broken out by HTTP status |
| Latency Percentiles by Route | Time series | P50/P90/P95 for every route on one chart |
| Latency Percentiles — $route | Bar chart (repeating) | P50/P75/P90/P95/P99 snapshot per route |

The **Route** variable at the top of the dashboard is populated live from Prometheus label values. The repeating bar chart creates one panel per route (3 per row), showing the current percentile distribution at a glance. Select specific routes from the dropdown to narrow the view.

## Running Without Docker

```bash
pip install -r requirements.txt
export CONFIG_PATH=config.yaml
python server.py
```

The service starts on the port in `config.yaml` (default 9004). OTLP export will fail gracefully if no collector is reachable.
