package metrics

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/metric"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
)

// Instruments holds all OTel metric instruments used by the server.
type Instruments struct {
	PermitWaitDuration  metric.Float64Histogram
	PermitHoldDuration  metric.Float64Histogram
	PermitActive        metric.Int64UpDownCounter
	PermitQueued        metric.Int64UpDownCounter
	PermitRequestTotal  metric.Int64Counter
	PermitIssuedTotal   metric.Int64Counter
	BackoffDuration     metric.Float64Histogram
	ResponseStatusTotal metric.Int64Counter
	RobotsFetchTotal    metric.Int64Counter
}

// Init sets up the OTel SDK and returns Instruments. Call Shutdown on the returned
// func when the process exits.
func Init(ctx context.Context) (*Instruments, func(), error) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:4317"
	}
	// otlpmetricgrpc expects host:port, not a full URL
	endpoint = strings.TrimPrefix(endpoint, "https://")
	endpoint = strings.TrimPrefix(endpoint, "http://")

	exporter, err := otlpmetricgrpc.New(ctx,
		otlpmetricgrpc.WithEndpoint(endpoint),
		otlpmetricgrpc.WithInsecure(),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("otlp exporter: %w", err)
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName("request-auth-server"),
		),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("otel resource: %w", err)
	}

	provider := sdkmetric.NewMeterProvider(
		sdkmetric.WithReader(
			sdkmetric.NewPeriodicReader(exporter, sdkmetric.WithInterval(15*time.Second)),
		),
		sdkmetric.WithResource(res),
	)
	otel.SetMeterProvider(provider)

	meter := provider.Meter("request-auth")

	inst, err := newInstruments(meter)
	if err != nil {
		return nil, nil, err
	}

	shutdown := func() {
		_ = provider.Shutdown(context.Background())
	}
	return inst, shutdown, nil
}

func newInstruments(meter metric.Meter) (*Instruments, error) {
	var err error
	inst := &Instruments{}

	inst.PermitWaitDuration, err = meter.Float64Histogram("permit.wait_duration_ms",
		metric.WithDescription("Time from PermitRequest to PermitGrant (ms)"),
		metric.WithUnit("ms"))
	if err != nil {
		return nil, err
	}

	inst.PermitHoldDuration, err = meter.Float64Histogram("permit.hold_duration_ms",
		metric.WithDescription("Time permit was held by client (ms)"),
		metric.WithUnit("ms"))
	if err != nil {
		return nil, err
	}

	inst.PermitActive, err = meter.Int64UpDownCounter("permit.active",
		metric.WithDescription("Currently held permits"))
	if err != nil {
		return nil, err
	}

	inst.PermitQueued, err = meter.Int64UpDownCounter("permit.queued",
		metric.WithDescription("Requests waiting in queue"))
	if err != nil {
		return nil, err
	}

	inst.PermitRequestTotal, err = meter.Int64Counter("permit.request_total",
		metric.WithDescription("Total permit requests received"))
	if err != nil {
		return nil, err
	}

	inst.PermitIssuedTotal, err = meter.Int64Counter("permit.issued_total",
		metric.WithDescription("Total permits issued"))
	if err != nil {
		return nil, err
	}

	inst.BackoffDuration, err = meter.Float64Histogram("permit.backoff_duration_ms",
		metric.WithDescription("Backoff delay applied after permit return (ms)"),
		metric.WithUnit("ms"))
	if err != nil {
		return nil, err
	}

	inst.ResponseStatusTotal, err = meter.Int64Counter("response.status_total",
		metric.WithDescription("Permit returns by HTTP status code"))
	if err != nil {
		return nil, err
	}

	inst.RobotsFetchTotal, err = meter.Int64Counter("robots_txt.fetch_total",
		metric.WithDescription("robots.txt fetch attempts by result"))
	if err != nil {
		return nil, err
	}

	return inst, nil
}

// DomainAttr returns an OTel attribute for the domain label.
func DomainAttr(domain string) attribute.KeyValue {
	return attribute.String("domain", domain)
}

// StatusAttr returns an OTel attribute for an HTTP status code.
func StatusAttr(code int32) attribute.KeyValue {
	return attribute.Int("status_code", int(code))
}

// ResultAttr returns an OTel attribute for a fetch result string.
func ResultAttr(result string) attribute.KeyValue {
	return attribute.String("result", result)
}
