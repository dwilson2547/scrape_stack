import { useEffect, useRef, useState } from "react";
import { useFilterStore } from "../store/useFilterStore";

export function FilterBar() {
  const {
    cacheType,
    q,
    clientName,
    dateFrom,
    dateTo,
    gridColumns,
    setQ,
    setClientName,
    setDateFrom,
    setDateTo,
    setGridColumns,
    setBucket,
    setPrefix,
  } = useFilterStore();

  const [localQ, setLocalQ] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalQ(q);
  }, [q]);

  const handleQChange = (val: string) => {
    setLocalQ(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setQ(val), 300);
  };

  const handleClear = () => {
    setLocalQ("");
    setQ("");
    setClientName(null);
    setDateFrom(null);
    setDateTo(null);
    setBucket(null);
    setPrefix(null);
  };

  const showGridSlider = cacheType === "image" || cacheType === "video";

  return (
    <div className="bg-white border-b border-gray-200 px-4 py-3 flex flex-wrap gap-3 items-center">
      <input
        type="search"
        placeholder="Search..."
        value={localQ}
        onChange={(e) => handleQChange(e.target.value)}
        className="border border-gray-300 rounded px-3 py-1.5 text-sm flex-1 min-w-48 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <input
        type="datetime-local"
        value={dateFrom ?? ""}
        onChange={(e) => setDateFrom(e.target.value || null)}
        className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        title="From date"
      />

      <input
        type="datetime-local"
        value={dateTo ?? ""}
        onChange={(e) => setDateTo(e.target.value || null)}
        className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        title="To date"
      />

      <input
        type="text"
        placeholder="Client name"
        value={clientName ?? ""}
        onChange={(e) => setClientName(e.target.value || null)}
        className="border border-gray-300 rounded px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      {showGridSlider && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600 whitespace-nowrap">
            Cols: {gridColumns}
          </label>
          <input
            type="range"
            min={2}
            max={8}
            value={gridColumns}
            onChange={(e) => setGridColumns(Number(e.target.value))}
            className="w-20"
          />
        </div>
      )}

      <button
        onClick={handleClear}
        className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded border border-gray-300 transition-colors"
      >
        Clear
      </button>
    </div>
  );
}
