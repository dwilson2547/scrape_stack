import { useBuckets, usePrefixes } from "../api/queries";
import { useFilterStore } from "../store/useFilterStore";
import type { CacheType } from "../types";

const CACHE_TYPES: { label: string; value: CacheType }[] = [
  { label: "Web", value: "web" },
  { label: "Image", value: "image" },
  { label: "File", value: "file" },
  { label: "Video", value: "video" },
];

export function Sidebar() {
  const {
    cacheType,
    bucket,
    prefix,
    setCacheType,
    setBucket,
    setPrefix,
  } = useFilterStore();

  const bucketsQuery = useBuckets(cacheType);
  const prefixesQuery = usePrefixes(cacheType, bucket);

  return (
    <aside className="w-60 shrink-0 bg-gray-900 text-gray-100 flex flex-col h-screen overflow-y-auto">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold mb-3 text-white">Cache Browser</h1>
        <div className="grid grid-cols-2 gap-1">
          {CACHE_TYPES.map((ct) => (
            <button
              key={ct.value}
              onClick={() => setCacheType(ct.value)}
              className={`px-2 py-1 rounded text-sm font-medium transition-colors ${
                cacheType === ct.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
            >
              {ct.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 p-3">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Buckets
        </div>

        {bucketsQuery.isLoading && (
          <div className="text-sm text-gray-500">Loading...</div>
        )}
        {bucketsQuery.isError && (
          <div className="text-sm text-red-400">Failed to load buckets</div>
        )}
        {bucketsQuery.data?.buckets.map((b) => (
          <div key={b}>
            <button
              onClick={() => setBucket(bucket === b ? null : b)}
              className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition-colors ${
                bucket === b
                  ? "bg-blue-700 text-white"
                  : "text-gray-300 hover:bg-gray-700"
              }`}
              title={b}
            >
              {b}
            </button>

            {bucket === b && (
              <div className="ml-3 mt-1 mb-1">
                {prefixesQuery.isLoading && (
                  <div className="text-xs text-gray-500 px-2">Loading...</div>
                )}
                {prefixesQuery.data?.prefixes.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPrefix(prefix === p ? null : p)}
                    className={`w-full text-left px-2 py-1 rounded text-xs truncate transition-colors ${
                      prefix === p
                        ? "bg-blue-600 text-white"
                        : "text-gray-400 hover:bg-gray-700"
                    }`}
                    title={p}
                  >
                    {p}
                  </button>
                ))}
                {prefixesQuery.data?.prefixes.length === 0 && (
                  <div className="text-xs text-gray-600 px-2">No prefixes</div>
                )}
              </div>
            )}
          </div>
        ))}

        {bucketsQuery.data?.buckets.length === 0 && (
          <div className="text-sm text-gray-600">No buckets</div>
        )}
      </div>
    </aside>
  );
}
