import type { CacheItem } from "../types";

interface Props {
  item: CacheItem;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function FileItem({ item }: Props) {
  const downloadName = item.filename ?? item.hash;
  const downloadHref = `/proxy/file/cache/${item.hash}`;

  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-200 hover:bg-gray-50">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-800 truncate">
          {item.filename ?? item.hash}
        </div>
        <div className="text-xs text-gray-500 truncate mt-0.5" title={item.url ?? ""}>
          {item.url ?? "—"}
        </div>
        <div className="flex gap-3 text-xs text-gray-400 mt-0.5">
          {item.mime_type && <span>{item.mime_type}</span>}
          {item.size_bytes != null && (
            <span>{formatBytes(item.size_bytes)}</span>
          )}
          <span>{new Date(item.created_at).toLocaleString()}</span>
          {item.client_name && <span>{item.client_name}</span>}
        </div>
      </div>
      <a
        href={downloadHref}
        download={downloadName}
        className="shrink-0 px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
      >
        Download
      </a>
    </div>
  );
}
