import { useBrowse } from "../api/queries";
import type { BrowseFilters } from "../api/client";
import type { CacheType } from "../types";

export function useInfiniteItems(cacheType: CacheType, filters: BrowseFilters) {
  const query = useBrowse(cacheType, filters);
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  return { ...query, items };
}
