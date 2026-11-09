export type CacheType = "web" | "image" | "file" | "video";

export interface CacheItem {
  hash: string;
  url: string | null;
  bucket: string | null;
  prefix: string | null;
  client_name: string | null;
  created_at: string;
  retrieved_at: string | null;
  cache_type: CacheType;
  // imgcache extras
  mime_type?: string;
  size_bytes?: number;
  width?: number;
  height?: number;
  // filecache / vidcache extras
  filename?: string;
  // vidcache extras
  duration_s?: number | null;
}

export interface BrowseResponse {
  items: CacheItem[];
  next_cursor: string | null;
}

export interface BucketResponse {
  buckets: string[];
}

export interface PrefixResponse {
  prefixes: string[];
}

export interface SearchResponse {
  items: CacheItem[];
  cache_types_searched: string[];
  errors: Record<string, string> | null;
}
