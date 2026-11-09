from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import generate_latest, REGISTRY

# Module-level noop placeholders — replaced by init_metrics() at startup.
# Callers use these as `metrics.store_counter.add(...)` with no if-guard needed.
_noop = otel_metrics.get_meter("imgcache")
store_counter = _noop.create_counter("imgcache.store.total")
lookup_counter = _noop.create_counter("imgcache.lookup.total")
image_bytes_histogram = _noop.create_histogram("imgcache.image_bytes")
perceptual_hash_counter = _noop.create_counter("imgcache.perceptual_hash.computed")
similar_search_counter = _noop.create_counter("imgcache.similar_search.total")

_meter_provider = None
_prometheus_reader = None


def _unregister_prometheus_reader():
    global _prometheus_reader
    if _prometheus_reader is not None:
        try:
            REGISTRY.unregister(_prometheus_reader._collector)
        except Exception:
            pass
        _prometheus_reader = None


def init_metrics(service_name: str, otlp_endpoint: str = ""):
    global _meter_provider, _prometheus_reader
    global store_counter, lookup_counter, image_bytes_histogram
    global perceptual_hash_counter, similar_search_counter

    _unregister_prometheus_reader()

    readers = []
    prometheus_reader = PrometheusMetricReader()
    _prometheus_reader = prometheus_reader
    readers.append(prometheus_reader)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)))
        except ImportError:
            pass

    _meter_provider = MeterProvider(metric_readers=readers)
    meter = _meter_provider.get_meter(service_name)

    store_counter = meter.create_counter("imgcache.store.total")
    lookup_counter = meter.create_counter("imgcache.lookup.total")
    image_bytes_histogram = meter.create_histogram("imgcache.image_bytes")
    perceptual_hash_counter = meter.create_counter("imgcache.perceptual_hash.computed")
    similar_search_counter = meter.create_counter("imgcache.similar_search.total")


def get_metrics_output() -> bytes:
    return generate_latest(REGISTRY)


def shutdown_metrics():
    global _meter_provider
    if _meter_provider:
        _meter_provider.shutdown()
        _meter_provider = None
    _unregister_prometheus_reader()
