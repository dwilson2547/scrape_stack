export interface Domain {
  id: number
  hostname: string
  pool_size: number | null
  base_delay_ms: number | null
  backoff_multiplier: number | null
  max_delay_ms: number | null
  recovery_threshold: number | null
  bucket_id: number | null
  created_at: string
  updated_at: string
}

export interface DomainCreate {
  hostname: string
  pool_size?: number | null
  base_delay_ms?: number | null
  backoff_multiplier?: number | null
  max_delay_ms?: number | null
  recovery_threshold?: number | null
  bucket_id?: number | null
}

export interface DomainUpdate {
  pool_size?: number | null
  base_delay_ms?: number | null
  backoff_multiplier?: number | null
  max_delay_ms?: number | null
  recovery_threshold?: number | null
  bucket_id?: number | null
}

export interface Bucket {
  id: number
  name: string
  pool_size: number | null
  base_delay_ms: number | null
  backoff_multiplier: number | null
  max_delay_ms: number | null
  recovery_threshold: number | null
  created_at: string
  updated_at: string
}

export interface BucketDetail extends Bucket {
  domains: Domain[]
}

export interface BucketCreate {
  name: string
  pool_size?: number | null
  base_delay_ms?: number | null
  backoff_multiplier?: number | null
  max_delay_ms?: number | null
  recovery_threshold?: number | null
}

export interface BucketUpdate {
  pool_size?: number | null
  base_delay_ms?: number | null
  backoff_multiplier?: number | null
  max_delay_ms?: number | null
  recovery_threshold?: number | null
}

export interface RobotsTxt {
  hostname: string
  crawl_delay_ms: number | null
  fetched_at: string | null
  not_found: boolean
  is_overridden: boolean
  override_delay_ms: number | null
}

export interface Config {
  default_pool_size: number
  default_base_delay_ms: number
  default_backoff_multiplier: number
  default_max_delay_ms: number
  default_recovery_threshold: number
  robots_txt_ttl_hours: number
  robots_txt_retry_hours: number
  config_reload_interval_seconds: number
}

export interface PoolStatus {
  domain: string
  pool_size: number
  active: number
  queued: number
  current_delay_ms: number
  consecutive_successes: number
}

export interface StatusResponse {
  pools: PoolStatus[]
}
