package pool

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestBackoffState_HappyPath(t *testing.T) {
	b := newBackoffState(1000, 60000, 3.0, 3)
	assert.Equal(t, int64(1000), b.CurrentDelayMs())

	b.Record(200)
	b.Record(200)
	assert.Equal(t, int64(1000), b.CurrentDelayMs()) // not yet at threshold

	b.Record(200) // hits threshold=3, decays (but already at base)
	assert.Equal(t, int64(1000), b.CurrentDelayMs())
}

func TestBackoffState_429IncreasesDelay(t *testing.T) {
	b := newBackoffState(1000, 60000, 3.0, 10)
	b.Record(429)
	assert.Equal(t, int64(3000), b.CurrentDelayMs())

	b.Record(429)
	assert.Equal(t, int64(9000), b.CurrentDelayMs())
}

func TestBackoffState_MaxDelayEnforced(t *testing.T) {
	b := newBackoffState(1000, 5000, 3.0, 10)
	b.Record(429) // 3000
	b.Record(429) // 9000 → clamped to 5000
	assert.Equal(t, int64(5000), b.CurrentDelayMs())
}

func TestBackoffState_DecayAfterThreshold(t *testing.T) {
	b := newBackoffState(1000, 60000, 3.0, 3)
	b.Record(429)
	assert.Equal(t, int64(3000), b.CurrentDelayMs())

	b.Record(200)
	b.Record(200)
	b.Record(200) // threshold=3 reached, decays to base
	assert.Equal(t, int64(1000), b.CurrentDelayMs())
}

func TestBackoffState_429ResetsConsecutive2xx(t *testing.T) {
	b := newBackoffState(1000, 60000, 3.0, 3)
	b.Record(429) // 3000
	b.Record(200)
	b.Record(200) // 2 of 3
	b.Record(429) // resets consecutive2xx, bumps to 9000
	assert.Equal(t, int64(9000), b.CurrentDelayMs())
}
