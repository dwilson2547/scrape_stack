import { useState } from "react";
import type { CacheItem } from "../types";
import { useFilterStore } from "../store/useFilterStore";

interface Props {
  item: CacheItem;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightText(text: string, keyword: string): string {
  const safe = escapeHtml(text);
  if (!keyword.trim()) return safe;
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(
    new RegExp(`(${escapedKeyword})`, "gi"),
    '<mark class="bg-yellow-200">$1</mark>'
  );
}

export function WebItem({ item }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const q = useFilterStore((s) => s.q);

  const handleExpand = async () => {
    if (!expanded && content === null && !loading) {
      setLoading(true);
      try {
        const bucket = encodeURIComponent(item.bucket ?? "default");
        const res = await fetch(`/proxy/web/cache/serve/${item.hash}?bucket=${bucket}`);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const text = await res.text();
        setContent(text);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    setExpanded((v) => !v);
  };

  return (
    <div className="border-b border-gray-200 hover:bg-gray-50">
      <button
        onClick={handleExpand}
        className="w-full text-left px-4 py-3 flex items-start gap-3"
      >
        <span className="text-gray-400 text-sm mt-0.5 shrink-0">
          {expanded ? "▼" : "▶"}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-blue-700 truncate font-medium">
            {item.url ?? "(no URL)"}
          </div>
          <div className="text-xs text-gray-500 mt-0.5 flex gap-3">
            {item.bucket && <span>{item.bucket}</span>}
            {item.prefix && <span>{item.prefix}</span>}
            <span>{new Date(item.created_at).toLocaleString()}</span>
            {item.client_name && <span>{item.client_name}</span>}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          {loading && (
            <div className="text-sm text-gray-500">Loading content...</div>
          )}
          {error && (
            <div className="text-sm text-red-500">Error: {error}</div>
          )}
          {content !== null && !loading && (
            <div className="overflow-auto max-h-96 rounded border border-gray-200 bg-gray-50">
              <pre
                className="text-xs p-3 whitespace-pre-wrap break-all"
                dangerouslySetInnerHTML={{
                  __html: highlightText(content, q),
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
