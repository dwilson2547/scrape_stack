import {
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";
import {
  fetchBrowse,
  fetchBuckets,
  fetchPrefixes,
  fetchSearch,
  type BrowseFilters,
  type SearchFilters,
} from "./client";
import type { CacheType } from "../types";

export function useBrowse(cacheType: CacheType, filters: BrowseFilters) {
  return useInfiniteQuery({
    queryKey: ["browse", cacheType, filters],
    queryFn: ({ pageParam }) =>
      fetchBrowse(cacheType, {
        ...filters,
        cursor: pageParam as string | undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useBuckets(cacheType: CacheType) {
  return useQuery({
    queryKey: ["buckets", cacheType],
    queryFn: () => fetchBuckets(cacheType),
  });
}

export function usePrefixes(cacheType: CacheType, bucket: string | null) {
  return useQuery({
    queryKey: ["prefixes", cacheType, bucket],
    queryFn: () => fetchPrefixes(cacheType, bucket!),
    enabled: bucket !== null && bucket !== "",
  });
}

export function useSearch(filters: SearchFilters) {
  return useQuery({
    queryKey: ["search", filters],
    queryFn: () => fetchSearch(filters),
    enabled: filters.q.trim() !== "",
  });
}
