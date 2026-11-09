from __future__ import annotations

from opentelemetry import metrics as _otel_metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from prometheus_client import REGISTRY, generate_latest

_meter_provider = None
_prometheus_reader = None

# Module-level noop instruments so callers can reference them unconditionally
# before init_metrics() is called.  init_metrics() replaces these with real
# instruments wired to a live MeterProvider.
_noop = _otel_metrics.get_meter("filecache-noop")
upload_init_total = _noop.create_counter("filecache.upload_init.total")
ingest_total = _noop.create_counter("filecache.ingest.total")
download_total = _noop.create_counter("filecache.download.total")
lookup_total = _noop.create_counter("filecache.lookup.total")
file_bytes_histogram = _noop.create_histogram("filecache.file_bytes")


def _unregister_prometheus() -> None:
    global _prometheus_reader
    if _prometheus_reader is not None:
        try:
            REGISTRY.unregister(_prometheus_reader._collector)
        except Exception:
            pass
        _prometheus_reader = None


def init_metrics(service_name: str, otlp_endpoint: str | None = None) -> None:
    global _meter_provider, _prometheus_reader
    global upload_init_total, ingest_total, download_total, lookup_total, file_bytes_histogram

    _unregister_prometheus()

    readers = []

    prometheus_reader = PrometheusMetricReader()
    _prometheus_reader = prometheus_reader
    readers.append(prometheus_reader)

    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))

    _meter_provider = MeterProvider(metric_readers=readers)
    meter = _meter_provider.get_meter(service_name)

    upload_init_total = meter.create_counter(
        "filecache.upload_init.total",
        description="Two-phase upload init requests",
    )
    ingest_total = meter.create_counter(
        "filecache.ingest.total",
        description="Completed file ingest operations",
    )
    download_total = meter.create_counter(
        "filecache.download.total",
        description="Server-side download operations",
    )
    lookup_total = meter.create_counter(
        "filecache.lookup.total",
        description="File retrieval requests",
    )
    file_bytes_histogram = meter.create_histogram(
        "filecache.file_bytes",
        description="Size in bytes of newly stored files",
    )


def get_metrics_output() -> bytes:
    if _prometheus_reader is None:
        return b""
    return generate_latest(REGISTRY)


def shutdown_metrics() -> None:
    global _meter_provider
    _unregister_prometheus()
    if _meter_provider:
        try:
            _meter_provider.shutdown()
        except Exception:
            pass
        _meter_provider = None
