CREATE TABLE IF NOT EXISTS buckets (
    id                  BIGSERIAL PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    pool_size           INTEGER,
    base_delay_ms       INTEGER,
    backoff_multiplier  REAL,
    max_delay_ms        INTEGER,
    recovery_threshold  INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS domains (
    id                  BIGSERIAL PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    bucket_id           INTEGER REFERENCES buckets(id) ON DELETE SET NULL,
    pool_size           INTEGER,
    base_delay_ms       INTEGER,
    backoff_multiplier  REAL,
    max_delay_ms        INTEGER,
    recovery_threshold  INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS robots_txt_cache (
    id                      BIGSERIAL PRIMARY KEY,
    domain                  TEXT    NOT NULL UNIQUE,
    raw_content             TEXT,
    crawl_delay_ms          INTEGER,
    fetched_at              TIMESTAMP,
    expires_at              TIMESTAMP,
    checked_at              TIMESTAMP,
    is_overridden           INTEGER NOT NULL DEFAULT 0,
    override_delay_ms       INTEGER,
    original_crawl_delay_ms INTEGER,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS global_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO global_config (key, value) VALUES
    ('default_pool_size',              '1'),
    ('default_base_delay_ms',          '1000'),
    ('default_backoff_multiplier',     '3.0'),
    ('default_max_delay_ms',           '60000'),
    ('default_recovery_threshold',     '10'),
    ('robots_txt_ttl_hours',           '24'),
    ('robots_txt_retry_hours',         '24'),
    ('config_reload_interval_seconds', '30')
ON CONFLICT (key) DO NOTHING;
