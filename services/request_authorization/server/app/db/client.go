package db

import (
	"database/sql"
	_ "embed"
	"fmt"
	"strconv"
	"time"

	_ "github.com/lib/pq"
)

//go:embed schema.sql
var schemaSQL string

type Client struct {
	db *sql.DB
}

func New(dsn string) (*Client, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	if err := initSchema(db); err != nil {
		return nil, fmt.Errorf("schema init: %w", err)
	}
	return &Client{db: db}, nil
}

func initSchema(db *sql.DB) error {
	_, err := db.Exec(schemaSQL)
	return err
}

func (c *Client) GetGlobalConfig() (GlobalConfig, error) {
	rows, err := c.db.Query(`SELECT key, value FROM global_config`)
	if err != nil {
		return GlobalConfig{}, err
	}
	defer rows.Close()

	m := make(map[string]string)
	for rows.Next() {
		var k, v string
		if err := rows.Scan(&k, &v); err != nil {
			return GlobalConfig{}, err
		}
		m[k] = v
	}

	pi := func(key string, def int64) int64 {
		if v, ok := m[key]; ok {
			if n, err := strconv.ParseInt(v, 10, 64); err == nil {
				return n
			}
		}
		return def
	}
	pf := func(key string, def float64) float64 {
		if v, ok := m[key]; ok {
			if f, err := strconv.ParseFloat(v, 64); err == nil {
				return f
			}
		}
		return def
	}

	return GlobalConfig{
		DefaultPoolSize:             pi("default_pool_size", 1),
		DefaultBaseDelayMs:          pi("default_base_delay_ms", 1000),
		DefaultBackoffMultiplier:    pf("default_backoff_multiplier", 3.0),
		DefaultMaxDelayMs:           pi("default_max_delay_ms", 60000),
		DefaultRecoveryThreshold:    pi("default_recovery_threshold", 10),
		RobotsTxtTTLHours:           pi("robots_txt_ttl_hours", 24),
		RobotsTxtRetryHours:         pi("robots_txt_retry_hours", 24),
		ConfigReloadIntervalSeconds: pi("config_reload_interval_seconds", 30),
	}, nil
}

func (c *Client) GetDomainWithBucket(name string) (*DomainRow, *BucketRow, error) {
	row := c.db.QueryRow(`
		SELECT d.id, d.name,
		       d.bucket_id, d.pool_size, d.base_delay_ms, d.backoff_multiplier, d.max_delay_ms, d.recovery_threshold,
		       b.id, b.name, b.pool_size, b.base_delay_ms, b.backoff_multiplier, b.max_delay_ms, b.recovery_threshold
		FROM domains d
		LEFT JOIN buckets b ON d.bucket_id = b.id
		WHERE d.name = $1`, name)

	var d DomainRow
	var bID, bPoolSize, bBaseDelay, bMaxDelay, bRecovery sql.NullInt64
	var bName sql.NullString
	var bMultiplier sql.NullFloat64
	var dBucketID, dPoolSize, dBaseDelay, dMaxDelay, dRecovery sql.NullInt64
	var dMultiplier sql.NullFloat64

	err := row.Scan(
		&d.ID, &d.Name,
		&dBucketID, &dPoolSize, &dBaseDelay, &dMultiplier, &dMaxDelay, &dRecovery,
		&bID, &bName, &bPoolSize, &bBaseDelay, &bMultiplier, &bMaxDelay, &bRecovery,
	)
	if err == sql.ErrNoRows {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}

	d.BucketID = NullInt64{Value: dBucketID.Int64, Valid: dBucketID.Valid}
	d.PoolSize = NullInt64{Value: dPoolSize.Int64, Valid: dPoolSize.Valid}
	d.BaseDelayMs = NullInt64{Value: dBaseDelay.Int64, Valid: dBaseDelay.Valid}
	d.BackoffMultiplier = NullFloat64{Value: dMultiplier.Float64, Valid: dMultiplier.Valid}
	d.MaxDelayMs = NullInt64{Value: dMaxDelay.Int64, Valid: dMaxDelay.Valid}
	d.RecoveryThreshold = NullInt64{Value: dRecovery.Int64, Valid: dRecovery.Valid}

	if !bID.Valid {
		return &d, nil, nil
	}
	bucket := &BucketRow{
		ID:                bID.Int64,
		Name:              bName.String,
		PoolSize:          NullInt64{Value: bPoolSize.Int64, Valid: bPoolSize.Valid},
		BaseDelayMs:       NullInt64{Value: bBaseDelay.Int64, Valid: bBaseDelay.Valid},
		BackoffMultiplier: NullFloat64{Value: bMultiplier.Float64, Valid: bMultiplier.Valid},
		MaxDelayMs:        NullInt64{Value: bMaxDelay.Int64, Valid: bMaxDelay.Valid},
		RecoveryThreshold: NullInt64{Value: bRecovery.Int64, Valid: bRecovery.Valid},
	}
	return &d, bucket, nil
}

func (c *Client) UpsertDomain(name string) error {
	_, err := c.db.Exec(`INSERT INTO domains (name) VALUES ($1) ON CONFLICT DO NOTHING`, name)
	return err
}

func (c *Client) GetRobotsTxt(domain string) (*RobotsTxtRow, error) {
	row := c.db.QueryRow(`
		SELECT domain, crawl_delay_ms,
		       EXTRACT(EPOCH FROM expires_at)::BIGINT * 1000,
		       EXTRACT(EPOCH FROM checked_at)::BIGINT * 1000,
		       is_overridden, override_delay_ms, original_crawl_delay_ms
		FROM robots_txt_cache WHERE domain = $1`, domain)

	var r RobotsTxtRow
	var crawlDelay, expiresMs, checkedMs, overrideMs, origMs sql.NullInt64
	var isOverridden int

	err := row.Scan(&r.Domain, &crawlDelay, &expiresMs, &checkedMs,
		&isOverridden, &overrideMs, &origMs)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	r.CrawlDelayMs = NullInt64{Value: crawlDelay.Int64, Valid: crawlDelay.Valid}
	r.ExpiresAtUnixMs = NullInt64{Value: expiresMs.Int64, Valid: expiresMs.Valid}
	r.CheckedAtUnixMs = NullInt64{Value: checkedMs.Int64, Valid: checkedMs.Valid}
	r.IsOverridden = isOverridden != 0
	r.OverrideDelayMs = NullInt64{Value: overrideMs.Int64, Valid: overrideMs.Valid}
	r.OrigCrawlDelayMs = NullInt64{Value: origMs.Int64, Valid: origMs.Valid}
	return &r, nil
}

func (c *Client) UpsertRobotsTxtSuccess(domain string, crawlDelayMs int64, ttlHours int64) error {
	expiresAt := time.Now().UTC().Add(time.Duration(ttlHours) * time.Hour)
	_, err := c.db.Exec(`
		INSERT INTO robots_txt_cache (domain, crawl_delay_ms, fetched_at, expires_at, checked_at)
		VALUES ($1, $2, NOW(), $3, NOW())
		ON CONFLICT (domain) DO UPDATE SET
			crawl_delay_ms = excluded.crawl_delay_ms,
			fetched_at     = excluded.fetched_at,
			expires_at     = excluded.expires_at,
			checked_at     = excluded.checked_at,
			updated_at     = NOW()
		WHERE robots_txt_cache.is_overridden = 0`,
		domain, crawlDelayMs, expiresAt)
	return err
}

func (c *Client) UpsertRobotsTxtNotFound(domain string, retryHours int64) error {
	expiresAt := time.Now().UTC().Add(time.Duration(retryHours) * time.Hour)
	_, err := c.db.Exec(`
		INSERT INTO robots_txt_cache (domain, checked_at, expires_at)
		VALUES ($1, NOW(), $2)
		ON CONFLICT (domain) DO UPDATE SET
			checked_at = NOW(),
			expires_at = $3,
			updated_at = NOW()`,
		domain, expiresAt, expiresAt)
	return err
}
