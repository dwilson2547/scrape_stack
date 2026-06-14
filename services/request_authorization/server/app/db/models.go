package db

type NullInt64 struct {
	Value int64
	Valid bool
}

type NullFloat64 struct {
	Value float64
	Valid bool
}

type DomainRow struct {
	ID                int64
	Name              string
	BucketID          NullInt64
	PoolSize          NullInt64
	BaseDelayMs       NullInt64
	BackoffMultiplier NullFloat64
	MaxDelayMs        NullInt64
	RecoveryThreshold NullInt64
}

type BucketRow struct {
	ID                int64
	Name              string
	PoolSize          NullInt64
	BaseDelayMs       NullInt64
	BackoffMultiplier NullFloat64
	MaxDelayMs        NullInt64
	RecoveryThreshold NullInt64
}

type RobotsTxtRow struct {
	Domain              string
	CrawlDelayMs        NullInt64
	ExpiresAtUnixMs     NullInt64
	CheckedAtUnixMs     NullInt64
	IsOverridden        bool
	OverrideDelayMs     NullInt64
	OrigCrawlDelayMs    NullInt64
}

type GlobalConfig struct {
	DefaultPoolSize             int64
	DefaultBaseDelayMs          int64
	DefaultBackoffMultiplier    float64
	DefaultMaxDelayMs           int64
	DefaultRecoveryThreshold    int64
	RobotsTxtTTLHours           int64
	RobotsTxtRetryHours         int64
	ConfigReloadIntervalSeconds int64
}
