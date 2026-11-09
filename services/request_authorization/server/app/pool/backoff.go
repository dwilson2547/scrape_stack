package pool

import "sync"

// BackoffState tracks per-domain adaptive delay. All state is in-memory; resets on restart.
type BackoffState struct {
	mu             sync.Mutex
	baseDelayMs    int64
	maxDelayMs     int64
	multiplier     float64
	threshold      int // consecutive 2xx before decay
	currentDelayMs int64
	consecutive2xx int
}

func newBackoffState(baseDelayMs, maxDelayMs int64, multiplier float64, threshold int) *BackoffState {
	return &BackoffState{
		baseDelayMs:    baseDelayMs,
		maxDelayMs:     maxDelayMs,
		multiplier:     multiplier,
		threshold:      threshold,
		currentDelayMs: baseDelayMs,
	}
}

func (b *BackoffState) Record(statusCode int32) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if statusCode == 429 {
		b.consecutive2xx = 0
		next := int64(float64(b.currentDelayMs) * b.multiplier)
		if next > b.maxDelayMs {
			next = b.maxDelayMs
		}
		b.currentDelayMs = next
		return
	}

	if statusCode >= 200 && statusCode < 300 {
		b.consecutive2xx++
		if b.consecutive2xx >= b.threshold {
			b.consecutive2xx = 0
			b.currentDelayMs = b.baseDelayMs
		}
	}
}

func (b *BackoffState) CurrentDelayMs() int64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.currentDelayMs
}

func (b *BackoffState) ConsecutiveSuccesses() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.consecutive2xx
}

func (b *BackoffState) UpdateConfig(baseDelayMs, maxDelayMs int64, multiplier float64, threshold int) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.multiplier = multiplier
	b.maxDelayMs = maxDelayMs
	b.threshold = threshold
	if b.currentDelayMs < baseDelayMs || b.baseDelayMs == b.currentDelayMs {
		b.currentDelayMs = baseDelayMs
	}
	b.baseDelayMs = baseDelayMs
}
