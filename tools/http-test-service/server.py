"""
rate-limit-testbed — configurable HTTP response generator with OpenTelemetry metrics.

Route modes (one active per route):
  probabilistic   reject_rate (0–1) fires a random rejection
  windowed        window_max + window_seconds enforces N req/window then rejects
  distribution    status_distribution: weighted list of {status, weight} entries

Built-in routes:
  /probe/<code>[/<path>]   always return the given HTTP status code (all methods)
  /robots.txt              served from config
  /_reset_windows          POST to reset all windowed counters (for testing)
"""

import os
import random
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
import uvicorn

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class StatusWeight:
    status: int
    weight: float = 1.0


@dataclass
class RobotRule:
    user_agent: str = "*"
    disallow: list = field(default_factory=list)
    allow: list = field(default_factory=list)
    crawl_delay: Optional[int] = None


@dataclass
class RouteConfig:
    path: str
    method: str = "GET"
    wildcard: bool = False          # also register path/{path:path}

    # success response
    status_ok: int = 200
    body: dict = field(default_factory=lambda: {"status": "ok"})

    # latency simulation
    latency_ms: int = 0
    jitter_ms: int = 0

    # --- rejection mode: only one is active ---
    # Mode 1: probabilistic
    reject_rate: float = 0.0
    reject_status: int = 429
    # Mode 2: windowed (takes precedence over probabilistic)
    window_max: Optional[int] = None
    window_seconds: int = 60
    # Mode 3: weighted distribution (takes precedence over all)
    status_distribution: Optional[list] = None  # list[StatusWeight]

    # --- response headers ---
    retry_after: Optional[int] = None
    retry_after_format: str = "seconds"  # "seconds" or "http_date"
    rate_limit_headers: bool = False     # emit X-RateLimit-* (windowed mode only)


@dataclass
class Config:
    service_name: str = "rate-limit-testbed"
    host: str = "0.0.0.0"
    port: int = 9004
    otlp_endpoint: str = "http://localhost:4317"
    metrics_export_interval_ms: int = 5000
    robots_txt: list = field(default_factory=list)  # list[RobotRule]
    routes: list = field(default_factory=list)       # list[RouteConfig]


def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    if not p.exists():
        print(f"[warn] {path} not found — using defaults")
        cfg = Config()
        cfg.routes = [
            RouteConfig(path="/api/resource", reject_rate=0.4, retry_after=2),
            RouteConfig(path="/api/fast",     reject_rate=0.1, retry_after=1, latency_ms=5),
            RouteConfig(path="/api/slow",     reject_rate=0.7, retry_after=5, latency_ms=200, jitter_ms=100),
        ]
        return cfg

    with open(p) as f:
        raw = yaml.safe_load(f)

    robot_rules = []
    for r in raw.pop("robots_txt", []):
        robot_rules.append(RobotRule(
            user_agent=r.get("user_agent", "*"),
            disallow=r.get("disallow") or [],
            allow=r.get("allow") or [],
            crawl_delay=r.get("crawl_delay"),
        ))

    routes = []
    for r in raw.pop("routes", []):
        dist_raw = r.pop("status_distribution", None)
        rc = RouteConfig(**r)
        if dist_raw:
            rc.status_distribution = [StatusWeight(**d) for d in dist_raw]
        routes.append(rc)

    return Config(**raw, robots_txt=robot_rules, routes=routes)


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def build_robots_txt(rules: list) -> str:
    lines = []
    for rule in rules:
        lines.append(f"User-agent: {rule.user_agent}")
        for path in (rule.allow or []):
            lines.append(f"Allow: {path}")
        for path in (rule.disallow or []):
            lines.append(f"Disallow: {path}")
        if rule.crawl_delay is not None:
            lines.append(f"Crawl-delay: {rule.crawl_delay}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# OTel
# ---------------------------------------------------------------------------

def init_otel(cfg: Config):
    resource = Resource.create({"service.name": cfg.service_name})
    exporter = OTLPMetricExporter(endpoint=cfg.otlp_endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=cfg.metrics_export_interval_ms)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter("rate_limit_testbed")
    counters = {
        "requests_total": meter.create_counter("http.server.requests_total",
                                               description="Total inbound requests"),
        "rejected_total": meter.create_counter("http.server.rejected_total",
                                               description="Requests that returned a non-2xx"),
        "accepted_total": meter.create_counter("http.server.accepted_total",
                                               description="Requests that returned a 2xx"),
    }
    histograms = {
        "duration": meter.create_histogram("http.server.duration_ms", unit="ms",
                                           description="Server-side request duration"),
    }
    return counters, histograms


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

cfg = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
counters, histograms = init_otel(cfg)
app = FastAPI(title=cfg.service_name)

robots_txt_content = (
    build_robots_txt(cfg.robots_txt) if cfg.robots_txt else "User-agent: *\nAllow: /\n"
)

# Per-route window state for windowed routes
_window_states: dict = {
    rc.path: {"count": 0, "window_start": time.time(), "lock": Lock()}
    for rc in cfg.routes
    if rc.window_max is not None
}


# ---------------------------------------------------------------------------
# Route handler factory
# ---------------------------------------------------------------------------

def _retry_after_value(seconds: int, fmt: str) -> str:
    if fmt == "http_date":
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + seconds))
    return str(seconds)


def build_route_handler(rc: RouteConfig):
    def handler(request: Request, path: str = ""):
        start = time.perf_counter()
        labels = {"http.route": rc.path, "http.method": rc.method.upper()}
        counters["requests_total"].add(1, labels)

        if rc.latency_ms or rc.jitter_ms:
            jitter = random.randint(-rc.jitter_ms, rc.jitter_ms) if rc.jitter_ms else 0
            delay = rc.latency_ms + jitter
            if delay > 0:
                time.sleep(delay / 1000.0)

        headers = {}
        status_code = rc.status_ok
        rejected = False

        if rc.status_distribution:
            statuses = [sw.status for sw in rc.status_distribution]
            weights = [sw.weight for sw in rc.status_distribution]
            status_code = random.choices(statuses, weights=weights)[0]
            rejected = status_code >= 400

        elif rc.window_max is not None:
            state = _window_states[rc.path]
            with state["lock"]:
                now = time.time()
                if now - state["window_start"] >= rc.window_seconds:
                    state["count"] = 0
                    state["window_start"] = now
                state["count"] += 1
                count = state["count"]
                window_reset = int(state["window_start"] + rc.window_seconds)

            rejected = count > rc.window_max
            status_code = rc.reject_status if rejected else rc.status_ok

            if rc.rate_limit_headers:
                headers["X-RateLimit-Limit"] = str(rc.window_max)
                headers["X-RateLimit-Remaining"] = str(max(0, rc.window_max - count))
                headers["X-RateLimit-Reset"] = str(window_reset)

        elif rc.reject_rate > 0 and random.random() < rc.reject_rate:
            rejected = True
            status_code = rc.reject_status

        if rejected and rc.retry_after is not None:
            headers["Retry-After"] = _retry_after_value(rc.retry_after, rc.retry_after_format)

        elapsed = (time.perf_counter() - start) * 1000
        histograms["duration"].record(elapsed, {**labels, "http.status_code": str(status_code)})

        if rejected:
            counters["rejected_total"].add(1, labels)
            return JSONResponse(
                status_code=status_code,
                content={"error": "rejected", "status": status_code},
                headers=headers,
            )

        counters["accepted_total"].add(1, labels)
        return JSONResponse(status_code=status_code, content=rc.body, headers=headers)

    return handler


# ---------------------------------------------------------------------------
# Register routes
# ---------------------------------------------------------------------------

# Probe: always return the requested status code, any method, any sub-path
_probe_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

async def _probe_handler(code: int, request: Request, path: str = ""):
    return Response(status_code=code)

app.add_api_route("/probe/{code}", _probe_handler, methods=_probe_methods, name="probe")
app.add_api_route("/probe/{code}/{path:path}", _probe_handler, methods=_probe_methods, name="probe_path")

# Configured routes (non-wildcard registered before wildcard to avoid shadowing)
for rc in cfg.routes:
    h = build_route_handler(rc)
    methods = [rc.method.upper()]
    app.add_api_route(rc.path, h, methods=methods, name=rc.path)
    if rc.wildcard:
        app.add_api_route(f"{rc.path}/{{path:path}}", h, methods=methods, name=f"{rc.path}_wildcard")


# ---------------------------------------------------------------------------
# Built-in endpoints
# ---------------------------------------------------------------------------

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return robots_txt_content


@app.post("/_reset_windows")
async def reset_windows():
    for state in _window_states.values():
        with state["lock"]:
            state["count"] = 0
            state["window_start"] = time.time()
    return {"status": "reset", "routes": list(_window_states.keys())}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/_config")
async def show_config():
    return {
        "service_name": cfg.service_name,
        "otlp_endpoint": cfg.otlp_endpoint,
        "routes": [
            {
                "path": r.path,
                "method": r.method,
                "wildcard": r.wildcard,
                "reject_rate": r.reject_rate,
                "reject_status": r.reject_status,
                "window_max": r.window_max,
                "window_seconds": r.window_seconds,
                "status_distribution": [
                    {"status": sw.status, "weight": sw.weight}
                    for sw in (r.status_distribution or [])
                ],
                "retry_after": r.retry_after,
                "retry_after_format": r.retry_after_format,
                "rate_limit_headers": r.rate_limit_headers,
                "latency_ms": r.latency_ms,
                "jitter_ms": r.jitter_ms,
            }
            for r in cfg.routes
        ],
    }


if __name__ == "__main__":
    print(f"Starting {cfg.service_name} on {cfg.host}:{cfg.port}")
    print(f"  OTLP → {cfg.otlp_endpoint}")
    print(f"  Built-in: /probe/<code>[/<path>]  /robots.txt  /_reset_windows")
    for r in cfg.routes:
        if r.status_distribution:
            mode = f"distribution={[sw.status for sw in r.status_distribution]}"
        elif r.window_max is not None:
            mode = f"windowed={r.window_max}req/{r.window_seconds}s"
        else:
            mode = f"{r.reject_status}@{r.reject_rate:.0%}"
        suffix = " [wildcard]" if r.wildcard else ""
        print(f"  {r.method:6s} {r.path:40s}  {mode}{suffix}")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")
