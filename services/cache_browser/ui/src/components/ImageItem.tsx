import type { CacheItem } from "../types";

interface Props {
  item: CacheItem;
}

export function ImageItem({ item }: Props) {
  const bucket = encodeURIComponent(item.bucket ?? "");
  const src = `/proxy/image/cache/serve/${item.hash}?bucket=${bucket}`;

  return (
    <div className="relative group aspect-square overflow-hidden rounded bg-gray-100">
      <img
        src={src}
        alt={item.url ?? item.hash}
        loading="lazy"
        className="w-full h-full object-cover"
        title={item.url ?? item.hash}
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-end justify-between p-1.5 opacity-0 group-hover:opacity-100">
        <a
          href={src}
          download={item.hash}
          onClick={(e) => e.stopPropagation()}
          className="bg-white/90 text-gray-800 text-xs px-2 py-1 rounded hover:bg-white"
        >
          ↓
        </a>
        <a
          href={src}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="bg-white/90 text-gray-800 text-xs px-2 py-1 rounded hover:bg-white"
        >
          ⤢
        </a>
      </div>
    </div>
  );
}
