package metrics

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

// collectGauge returns metric name's points as domain → value.
func collectGauge(t *testing.T, reader *sdkmetric.ManualReader, name string) map[string]int64 {
	t.Helper()
	var rm metricdata.ResourceMetrics
	require.NoError(t, reader.Collect(context.Background(), &rm))
	out := map[string]int64{}
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			if m.Name != name {
				continue
			}
			for _, dp := range m.Data.(metricdata.Gauge[int64]).DataPoints {
				domain, _ := dp.Attributes.Value("domain")
				out[domain.AsString()] = dp.Value
			}
		}
	}
	return out
}

func TestObservePools_ReportsLivePoolState(t *testing.T) {
	reader := sdkmetric.NewManualReader()
	inst, err := newInstruments(sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader)).Meter("test"))
	require.NoError(t, err)

	pools := []PoolCounts{{Domain: "a.example", Active: 1, Queued: 2}, {Domain: "b.example", Active: 0, Queued: 0}}
	require.NoError(t, inst.ObservePools(func() []PoolCounts { return pools }))

	assert.Equal(t, map[string]int64{"a.example": 1, "b.example": 0}, collectGauge(t, reader, "permit.active"))
	assert.Equal(t, map[string]int64{"a.example": 2, "b.example": 0}, collectGauge(t, reader, "permit.queued"))

	// A client that disconnects holding a permit frees it in the pool without returning it;
	// the gauge follows the pool rather than staying at 1.
	pools = []PoolCounts{{Domain: "a.example"}, {Domain: "b.example"}}
	assert.Equal(t, map[string]int64{"a.example": 0, "b.example": 0}, collectGauge(t, reader, "permit.active"))
}
