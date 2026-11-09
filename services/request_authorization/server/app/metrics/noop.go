package metrics

import (
	"go.opentelemetry.io/otel/metric/noop"
)

// NewNoop returns an Instruments struct wired to no-op recorders.
// Used when OTel initialisation fails so the server still starts.
func NewNoop() *Instruments {
	m := noop.NewMeterProvider().Meter("noop")
	inst, _ := newInstruments(m)
	return inst
}
