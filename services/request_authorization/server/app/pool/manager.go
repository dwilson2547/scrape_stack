package pool

import (
	"context"
	"log"
	"sync"
	"time"

	"go.opentelemetry.io/otel/metric"

	"github.com/dwilson/request-auth/db"
	"github.com/dwilson/request-auth/metrics"
	pb "github.com/dwilson/request-auth/proto"
	"github.com/dwilson/request-auth/robots"
)

// Manager owns all per-domain pools and handles config reload.
type Manager struct {
	mu             sync.RWMutex
	pools          map[string]*Pool
	dbClient       *db.Client
	inst           *metrics.Instruments
	globalConfig   db.GlobalConfig
	reloadInterval time.Duration
}

func NewManager(dbClient *db.Client, inst *metrics.Instruments) (*Manager, error) {
	cfg, err := dbClient.GetGlobalConfig()
	if err != nil {
		return nil, err
	}
	m := &Manager{
		pools:          make(map[string]*Pool),
		dbClient:       dbClient,
		inst:           inst,
		globalConfig:   cfg,
		reloadInterval: time.Duration(cfg.ConfigReloadIntervalSeconds) * time.Second,
	}
	go m.reloadLoop()
	return m, nil
}

func (m *Manager) Acquire(ctx context.Context, clientID, domain string, reqID int64) (*pb.PermitGrant, error) {
	return m.getOrCreate(domain).Acquire(ctx, clientID, reqID)
}

// Return releases the permit and returns the domain it belonged to (empty if not found)
// and how long the permit was held.
func (m *Manager) Return(permitID string, statusCode int32) (string, time.Duration) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for domain, p := range m.pools {
		if p.HasPermit(permitID) {
			holdDuration := p.Return(permitID, statusCode)
			return domain, holdDuration
		}
	}
	return "", 0
}

func (m *Manager) DisconnectClient(clientID string) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, p := range m.pools {
		p.DisconnectClient(clientID)
	}
}

func (m *Manager) AllStatuses() []PoolStatus {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]PoolStatus, 0, len(m.pools))
	for _, p := range m.pools {
		out = append(out, p.Status())
	}
	return out
}

func (m *Manager) getOrCreate(domain string) *Pool {
	m.mu.RLock()
	if p, ok := m.pools[domain]; ok {
		m.mu.RUnlock()
		return p
	}
	m.mu.RUnlock()

	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pools[domain]; ok {
		return p
	}

	cfg := m.resolveConfig(domain)
	p := NewPool(domain, cfg)
	m.pools[domain] = p
	go m.initDomain(domain)
	return p
}

// resolveConfig builds a Config for domain using the priority chain:
// domain override → bucket → robots.txt crawl-delay → global default.
func (m *Manager) resolveConfig(domain string) Config {
	global := m.globalConfig
	base := Config{
		PoolSize:          int(global.DefaultPoolSize),
		BaseDelayMs:       global.DefaultBaseDelayMs,
		BackoffMultiplier: global.DefaultBackoffMultiplier,
		MaxDelayMs:        global.DefaultMaxDelayMs,
		RecoveryThreshold: int(global.DefaultRecoveryThreshold),
	}

	domRow, bucketRow, err := m.dbClient.GetDomainWithBucket(domain)
	if err != nil || domRow == nil {
		return base
	}

	// Start from bucket if present, then layer domain overrides
	if bucketRow != nil {
		if bucketRow.PoolSize.Valid {
			base.PoolSize = int(bucketRow.PoolSize.Value)
		}
		if bucketRow.BaseDelayMs.Valid {
			base.BaseDelayMs = bucketRow.BaseDelayMs.Value
		}
		if bucketRow.BackoffMultiplier.Valid {
			base.BackoffMultiplier = bucketRow.BackoffMultiplier.Value
		}
		if bucketRow.MaxDelayMs.Valid {
			base.MaxDelayMs = bucketRow.MaxDelayMs.Value
		}
		if bucketRow.RecoveryThreshold.Valid {
			base.RecoveryThreshold = int(bucketRow.RecoveryThreshold.Value)
		}
	}

	// Apply robots.txt crawl-delay as base_delay_ms if no explicit override
	robots, err := m.dbClient.GetRobotsTxt(domain)
	if err == nil && robots != nil && !robots.IsOverridden && robots.CrawlDelayMs.Valid {
		if !domRow.BaseDelayMs.Valid && !domRow.BucketID.Valid {
			base.BaseDelayMs = robots.CrawlDelayMs.Value
		}
	}
	if err == nil && robots != nil && robots.IsOverridden && robots.OverrideDelayMs.Valid {
		if !domRow.BaseDelayMs.Valid && !domRow.BucketID.Valid {
			base.BaseDelayMs = robots.OverrideDelayMs.Value
		}
	}

	// Domain-specific overrides win over everything
	if domRow.PoolSize.Valid {
		base.PoolSize = int(domRow.PoolSize.Value)
	}
	if domRow.BaseDelayMs.Valid {
		base.BaseDelayMs = domRow.BaseDelayMs.Value
	}
	if domRow.BackoffMultiplier.Valid {
		base.BackoffMultiplier = domRow.BackoffMultiplier.Value
	}
	if domRow.MaxDelayMs.Valid {
		base.MaxDelayMs = domRow.MaxDelayMs.Value
	}
	if domRow.RecoveryThreshold.Valid {
		base.RecoveryThreshold = int(domRow.RecoveryThreshold.Value)
	}

	return base
}

// initDomain inserts the domain row and performs an async robots.txt fetch.
func (m *Manager) initDomain(domain string) {
	if err := m.dbClient.UpsertDomain(domain); err != nil {
		log.Printf("upsert domain %s: %v", domain, err)
	}

	m.mu.RLock()
	ttlHours := m.globalConfig.RobotsTxtTTLHours
	retryHours := m.globalConfig.RobotsTxtRetryHours
	m.mu.RUnlock()

	result, err := robots.Fetch(domain)
	if err != nil {
		log.Printf("robots.txt fetch %s: %v", domain, err)
		_ = m.dbClient.UpsertRobotsTxtNotFound(domain, retryHours)
		m.inst.RobotsFetchTotal.Add(context.Background(), 1,
			metric.WithAttributes(metrics.ResultAttr("error")))
		return
	}
	if !result.Found {
		_ = m.dbClient.UpsertRobotsTxtNotFound(domain, retryHours)
		m.inst.RobotsFetchTotal.Add(context.Background(), 1,
			metric.WithAttributes(metrics.ResultAttr("not_found")))
		return
	}
	if err := m.dbClient.UpsertRobotsTxtSuccess(domain, result.CrawlDelayMs, ttlHours); err != nil {
		log.Printf("upsert robots.txt %s: %v", domain, err)
	}
	m.inst.RobotsFetchTotal.Add(context.Background(), 1,
		metric.WithAttributes(metrics.ResultAttr("success")))
}

func (m *Manager) reloadLoop() {
	ticker := time.NewTicker(m.reloadInterval)
	defer ticker.Stop()
	for range ticker.C {
		if err := m.reload(); err != nil {
			log.Printf("config reload: %v", err)
		}
	}
}

func (m *Manager) reload() error {
	cfg, err := m.dbClient.GetGlobalConfig()
	if err != nil {
		return err
	}
	m.mu.Lock()
	m.globalConfig = cfg
	pools := make(map[string]*Pool, len(m.pools))
	for k, v := range m.pools {
		pools[k] = v
	}
	m.mu.Unlock()

	for domain, p := range pools {
		newCfg := m.resolveConfig(domain)
		p.UpdateConfig(newCfg)
	}
	return nil
}
