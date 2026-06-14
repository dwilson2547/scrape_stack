import { useMemo } from "react";
import { useFilterStore } from "../store/useFilterStore";
import { useSearch } from "../api/queries";
import { useInfiniteItems } from "../hooks/useInfiniteItems";
import { WebList } from "./WebList";
import { ImageGrid } from "./ImageGrid";
import { VideoGrid } from "./VideoGrid";
import { FileList } from "./FileList";
import type { CacheItem } from "../types";

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
      No items found
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex items-center justify-center text-red-500 text-sm">
      Error: {message}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
      Loading...
    </div>
  );
}

interface ContentProps {
  items: CacheItem[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}

function ContentSwitch({
  items,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: ContentProps) {
  const cacheType = useFilterStore((s) => s.cacheType);

  if (cacheType === "web") {
    return (
      <WebList
        items={items}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        fetchNextPage={fetchNextPage}
      />
    );
  }
  if (cacheType === "image") {
    return (
      <ImageGrid
        items={items}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        fetchNextPage={fetchNextPage}
      />
    );
  }
  if (cacheType === "video") {
    return (
      <VideoGrid
        items={items}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        fetchNextPage={fetchNextPage}
      />
    );
  }
  return (
    <FileList
      items={items}
      hasNextPage={hasNextPage}
      isFetchingNextPage={isFetchingNextPage}
      fetchNextPage={fetchNextPage}
    />
  );
}

function BrowseContent() {
  const { cacheType, bucket, prefix, clientName, dateFrom, dateTo, q } =
    useFilterStore();

  const filters = useMemo(
    () => ({
      bucket,
      prefix,
      client_name: clientName,
      date_from: dateFrom,
      date_to: dateTo,
      q: q || undefined,
      limit: 50,
    }),
    [bucket, prefix, clientName, dateFrom, dateTo, q]
  );

  const {
    items,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useInfiniteItems(cacheType, filters);

  if (isLoading) return <LoadingState />;
  if (isError)
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "Unknown error"}
      />
    );
  if (items.length === 0) return <EmptyState />;

  return (
    <ContentSwitch
      items={items}
      hasNextPage={!!hasNextPage}
      isFetchingNextPage={isFetchingNextPage}
      fetchNextPage={fetchNextPage}
    />
  );
}

function SearchContent() {
  const { clientName, dateFrom, dateTo, q } = useFilterStore();

  const { data, isLoading, isError, error } = useSearch({
    q,
    date_from: dateFrom,
    date_to: dateTo,
    client_name: clientName,
  });

  if (isLoading) return <LoadingState />;
  if (isError)
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "Unknown error"}
      />
    );

  const items = data?.items ?? [];

  if (items.length === 0) return <EmptyState />;

  // Search results are mixed cache types — group by type and render each section
  const grouped = items.reduce<Record<string, CacheItem[]>>((acc, item) => {
    if (!acc[item.cache_type]) acc[item.cache_type] = [];
    acc[item.cache_type].push(item);
    return acc;
  }, {});

  return (
    <div className="flex-1 overflow-y-auto">
      {data?.errors && Object.keys(data.errors).length > 0 && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-xs text-yellow-700">
          Some caches returned errors:{" "}
          {Object.entries(data.errors)
            .map(([k, v]) => `${k}: ${v}`)
            .join(", ")}
        </div>
      )}
      {Object.entries(grouped).map(([type, typeItems]) => (
        <div key={type}>
          <div className="px-4 py-2 bg-gray-100 text-xs font-semibold text-gray-600 uppercase tracking-wider border-b">
            {type} ({typeItems.length})
          </div>
          {typeItems.map((item) => {
            if (type === "image") {
              return (
                <div key={item.hash} className="border-b border-gray-200 px-4 py-2 flex items-center gap-3">
                  <img
                    src={`/proxy/image/cache/serve/${item.hash}?bucket=${encodeURIComponent(item.bucket ?? "")}`}
                    className="w-12 h-12 object-cover rounded"
                    loading="lazy"
                    alt={item.url ?? item.hash}
                  />
                  <div className="text-sm text-gray-700 truncate">{item.url ?? item.hash}</div>
                </div>
              );
            }
            if (type === "file") {
              return (
                <div key={item.hash} className="border-b border-gray-200 px-4 py-2 flex items-center gap-3">
                  <span className="text-sm flex-1 truncate">{item.filename ?? item.url ?? item.hash}</span>
                  <a
                    href={`/proxy/file/cache/${item.hash}`}
                    download={item.filename ?? item.hash}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Download
                  </a>
                </div>
              );
            }
            if (type === "video") {
              return (
                <div key={item.hash} className="border-b border-gray-200 px-4 py-2 text-sm text-gray-700 truncate">
                  {item.filename ?? item.url ?? item.hash}
                </div>
              );
            }
            // web
            return (
              <div key={item.hash} className="border-b border-gray-200 px-4 py-2 text-sm text-gray-700 truncate">
                {item.url ?? item.hash}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function BrowsePane() {
  const { q, bucket } = useFilterStore();
  const isSearchMode = q.trim() !== "" && bucket === null;
  const isScopedSearch = q.trim() !== "" && bucket !== null;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {isScopedSearch && (
        <div className="bg-blue-50 border-b border-blue-200 px-4 py-1.5 text-xs text-blue-700">
          Searching within bucket <span className="font-semibold">{bucket}</span>. Clear the bucket selection to search all caches.
        </div>
      )}
      {isSearchMode ? <SearchContent /> : <BrowseContent />}
    </div>
  );
}
