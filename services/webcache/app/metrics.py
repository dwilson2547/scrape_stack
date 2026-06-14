import os

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# Module-level placeholders replaced by setup_metrics() at startup.
# Routes must access these as `metrics.store_total` (not `from metrics import store_total`)
# so they pick up the real instruments after setup.
_noop = otel_metrics.get_meter("webcache")
store_total = _noop.create_counter("webcache.store.total")
lookup_total = _noop.create_counter("webcache.lookup.total")
compressed_bytes = _noop.create_histogram("webcache.compressed.bytes")
render_total = _noop.create_counter("webcache.render.total")
render_duration = _noop.create_histogram("webcache.render.duration.seconds")


def setup_metrics(service_name: str = "webcache") -> None:
    global store_total, lookup_total, compressed_bytes, render_total, render_duration

    resource = Resource({SERVICE_NAME: service_name})
    readers = []

    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))

    views = [
        View(
            instrument_name="webcache.compressed.bytes",
            aggregation=ExplicitBucketHistogramAggregation(
                [1_024, 8_192, 32_768, 131_072, 524_288, 2_097_152, 8_388_608]
            ),
        ),
        View(
            instrument_name="webcache.render.duration.seconds",
            aggregation=ExplicitBucketHistogramAggregation(
                [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
            ),
        ),
    ]

    provider = MeterProvider(resource=resource, metric_readers=readers, views=views)
    otel_metrics.set_meter_provider(provider)

    meter = otel_metrics.get_meter("webcache")
    store_total = meter.create_counter("webcache.store.total", description="Page store requests")
    lookup_total = meter.create_counter("webcache.lookup.total", description="Cache lookup requests")
    compressed_bytes = meter.create_histogram("webcache.compressed.bytes", description="LZ4-compressed page size in bytes")
    render_total = meter.create_counter("webcache.render.total", description="Render requests")
    render_duration = meter.create_histogram("webcache.render.duration.seconds", description="Browserless render latency in seconds")
