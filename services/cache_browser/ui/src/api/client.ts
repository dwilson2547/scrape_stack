import type {
  BrowseResponse,
  BucketResponse,
  CacheType,
  PrefixResponse,
  SearchResponse,
} from "../types";

async function apiFetch<T>(
  path: string,
  params?: Record<string, string | number | undefined | null>
): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, String(v));
      }
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface BrowseFilters {
  bucket?: string | null;
  prefix?: string | null;
  client_name?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  q?: string;
  cursor?: string;
  limit?: number;
  order?: string;
}

export function fetchBrowse(
  cacheType: CacheType,
  filters: BrowseFilters
): Promise<BrowseResponse> {
  return apiFetch<BrowseResponse>(`/api/browse/${cacheType}`, {
    bucket: filters.bucket,
    prefix: filters.prefix,
    client_name: filters.client_name,
    date_from: filters.date_from,
    date_to: filters.date_to,
    q: filters.q,
    cursor: filters.cursor,
    limit: filters.limit,
    order: filters.order,
  });
}

export function fetchBuckets(cacheType: CacheType): Promise<BucketResponse> {
  return apiFetch<BucketResponse>(`/api/browse/${cacheType}/buckets`);
}

export function fetchPrefixes(
  cacheType: CacheType,
  bucket: string
): Promise<PrefixResponse> {
  return apiFetch<PrefixResponse>(`/api/browse/${cacheType}/prefixes`, {
    bucket,
  });
}

export interface SearchFilters {
  q: string;
  limit?: number;
  date_from?: string | null;
  date_to?: string | null;
  client_name?: string | null;
  cache_types?: string;
}

export function fetchSearch(filters: SearchFilters): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(`/api/search`, {
    q: filters.q,
    limit: filters.limit,
    date_from: filters.date_from,
    date_to: filters.date_to,
    client_name: filters.client_name,
    cache_types: filters.cache_types,
  });
}
