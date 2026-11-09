import os

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# Module-level placeholders replaced by setup_metrics() at startup.
# Callers must access these as `metrics.upload_init_total` (not via import)
# so they pick up the real instruments after setup.
_noop = otel_metrics.get_meter("vidcache")
upload_init_total = _noop.create_counter("vidcache.upload_init.total")
ingest_total = _noop.create_counter("vidcache.ingest.total")
lookup_total = _noop.create_counter("vidcache.lookup.total")
video_bytes = _noop.create_histogram("vidcache.video_bytes")
video_duration_seconds = _noop.create_histogram("vidcache.video_duration_seconds")
phash_distance = _noop.create_histogram("vidcache.phash_distance")


def setup_metrics(service_name: str = "vidcache") -> None:
    global upload_init_total, ingest_total, lookup_total
    global video_bytes, video_duration_seconds, phash_distance

    resource = Resource({SERVICE_NAME: service_name})
    readers = []

    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))

    views = [
        View(
            instrument_name="vidcache.video_bytes",
            aggregation=ExplicitBucketHistogramAggregation(
                [1_048_576, 10_485_760, 52_428_800, 104_857_600,
                 524_288_000, 1_073_741_824, 2_147_483_648]
            ),
        ),
        View(
            instrument_name="vidcache.video_duration_seconds",
            aggregation=ExplicitBucketHistogramAggregation(
                [5.0, 15.0, 30.0, 60.0, 180.0, 600.0, 1800.0]
            ),
        ),
        View(
            instrument_name="vidcache.phash_distance",
            aggregation=ExplicitBucketHistogramAggregation(
                [0, 1, 2, 3, 5, 8, 10]
            ),
        ),
    ]

    provider = MeterProvider(resource=resource, metric_readers=readers, views=views)
    otel_metrics.set_meter_provider(provider)

    meter = otel_metrics.get_meter("vidcache")
    upload_init_total = meter.create_counter(
        "vidcache.upload_init.total",
        description="Upload init requests (cached = URL already known, pending = new upload started)",
    )
    ingest_total = meter.create_counter(
        "vidcache.ingest.total",
        description="Ingest pipeline completions by result (new / duplicate / url_alias)",
    )
    lookup_total = meter.create_counter(
        "vidcache.lookup.total",
        description="Video lookup requests by result (hit / miss)",
    )
    video_bytes = meter.create_histogram(
        "vidcache.video_bytes",
        description="Raw size of newly stored videos in bytes",
    )
    video_duration_seconds = meter.create_histogram(
        "vidcache.video_duration_seconds",
        description="Duration of newly stored videos in seconds",
    )
    phash_distance = meter.create_histogram(
        "vidcache.phash_distance",
        description="Hamming distance of perceptual-hash duplicates",
    )
