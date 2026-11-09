package pool

import (
	"context"
	"sync"
	"time"

	"github.com/google/uuid"
	pb "github.com/dwilson/request-auth/proto"
)

// Config holds the resolved rate-limit settings for one domain.
type Config struct {
	PoolSize          int
	BaseDelayMs       int64
	BackoffMultiplier float64
	MaxDelayMs        int64
	RecoveryThreshold int
}

type heldPermit struct {
	permitID  string
	clientID  string
	grantedAt time.Time
}

type acquireResult struct {
	grant *pb.PermitGrant
	err   error
}

type waiter struct {
	reqID    int64
	clientID string
	ch       chan acquireResult
}

// Pool manages a fixed-size permit pool for one domain.
type Pool struct {
	mu           sync.Mutex
	domain       string
	config       Config
	available    int
	backoffCount int
	held         map[string]*heldPermit
	waiters      []*waiter
	backoff      *BackoffState
}

func NewPool(domain string, cfg Config) *Pool {
	return &Pool{
		domain:    domain,
		config:    cfg,
		available: cfg.PoolSize,
		held:      make(map[string]*heldPermit),
		backoff:   newBackoffState(cfg.BaseDelayMs, cfg.MaxDelayMs, cfg.BackoffMultiplier, cfg.RecoveryThreshold),
	}
}

// Acquire blocks until a permit is available or ctx is cancelled.
func (p *Pool) Acquire(ctx context.Context, clientID string, reqID int64) (*pb.PermitGrant, error) {
	p.mu.Lock()
	if p.available > 0 {
		p.available--
		grant := p.issueGrant(clientID, reqID)
		p.mu.Unlock()
		return grant, nil
	}

	ch := make(chan acquireResult, 1)
	w := &waiter{reqID: reqID, clientID: clientID, ch: ch}
	p.waiters = append(p.waiters, w)
	p.mu.Unlock()

	select {
	case result := <-ch:
		return result.grant, result.err
	case <-ctx.Done():
		p.removeWaiter(w)
		return nil, ctx.Err()
	}
}

func (p *Pool) issueGrant(clientID string, reqID int64) *pb.PermitGrant {
	permitID := uuid.New().String()
	p.held[permitID] = &heldPermit{
		permitID:  permitID,
		clientID:  clientID,
		grantedAt: time.Now(),
	}
	ttlMs := int32(p.backoff.CurrentDelayMs()) * int32(p.config.PoolSize+1)
	if ttlMs < int32(p.config.BaseDelayMs) {
		ttlMs = int32(p.config.BaseDelayMs)
	}
	return &pb.PermitGrant{PermitId: permitID, ReqId: reqID, TtlMs: ttlMs}
}

// Return releases a permit and schedules the next grant after backoff.
// Returns how long the permit was held (0 if not found).
func (p *Pool) Return(permitID string, statusCode int32) time.Duration {
	p.mu.Lock()
	hp, ok := p.held[permitID]
	if !ok {
		p.mu.Unlock()
		return 0
	}
	holdDuration := time.Since(hp.grantedAt)
	delete(p.held, permitID)
	p.backoff.Record(statusCode)
	delay := p.backoff.CurrentDelayMs()
	p.backoffCount++
	p.mu.Unlock()

	time.AfterFunc(time.Duration(delay)*time.Millisecond, func() {
		p.mu.Lock()
		p.backoffCount--
		inFlight := len(p.held) + p.backoffCount
		if len(p.waiters) > 0 && inFlight < p.config.PoolSize {
			w := p.waiters[0]
			p.waiters = p.waiters[1:]
			grant := p.issueGrant(w.clientID, w.reqID)
			p.mu.Unlock()
			w.ch <- acquireResult{grant: grant}
		} else if len(p.waiters) == 0 && p.available < p.config.PoolSize {
			p.available++
			p.mu.Unlock()
		} else {
			// Excess permit from a pool shrink — drain without re-issuing.
			p.mu.Unlock()
		}
	})

	return holdDuration
}

// DisconnectClient returns all permits held by clientID with status 0.
func (p *Pool) DisconnectClient(clientID string) {
	p.mu.Lock()
	var toReturn []string
	for permitID, h := range p.held {
		if h.clientID == clientID {
			toReturn = append(toReturn, permitID)
		}
	}
	filtered := p.waiters[:0]
	for _, w := range p.waiters {
		if w.clientID == clientID {
			w.ch <- acquireResult{err: context.Canceled}
		} else {
			filtered = append(filtered, w)
		}
	}
	p.waiters = filtered
	p.mu.Unlock()

	for _, id := range toReturn {
		p.Return(id, 0)
	}
}

// HasPermit reports whether permitID is currently held in this pool.
func (p *Pool) HasPermit(permitID string) bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	_, ok := p.held[permitID]
	return ok
}

// Status returns a snapshot of pool state for the /status endpoint.
func (p *Pool) Status() PoolStatus {
	p.mu.Lock()
	defer p.mu.Unlock()
	return PoolStatus{
		Domain:               p.domain,
		PoolSize:             p.config.PoolSize,
		Active:               len(p.held),
		Queued:               len(p.waiters),
		InBackoff:            p.backoffCount,
		CurrentDelayMs:       p.backoff.CurrentDelayMs(),
		ConsecutiveSuccesses: p.backoff.ConsecutiveSuccesses(),
	}
}

func (p *Pool) UpdateConfig(cfg Config) {
	p.mu.Lock()
	// Clamp available so a pool-size decrease doesn't leave phantom free slots.
	if maxAvail := cfg.PoolSize - len(p.held) - p.backoffCount; p.available > maxAvail {
		if maxAvail < 0 {
			maxAvail = 0
		}
		p.available = maxAvail
	}
	p.config = cfg
	p.mu.Unlock()
	p.backoff.UpdateConfig(cfg.BaseDelayMs, cfg.MaxDelayMs, cfg.BackoffMultiplier, cfg.RecoveryThreshold)
}

func (p *Pool) removeWaiter(w *waiter) {
	p.mu.Lock()
	defer p.mu.Unlock()
	filtered := p.waiters[:0]
	for _, existing := range p.waiters {
		if existing != w {
			filtered = append(filtered, existing)
		}
	}
	p.waiters = filtered
}

type PoolStatus struct {
	Domain               string `json:"domain"`
	PoolSize             int    `json:"pool_size"`
	Active               int    `json:"active"`
	Queued               int    `json:"queued"`
	InBackoff            int    `json:"in_backoff"`
	CurrentDelayMs       int64  `json:"current_delay_ms"`
	ConsecutiveSuccesses int    `json:"consecutive_successes"`
}
