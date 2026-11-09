import { useEffect, useRef } from "react";
import type { CacheItem } from "../types";
import { ImageItem } from "./ImageItem";
import { useFilterStore } from "../store/useFilterStore";

interface Props {
  items: CacheItem[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}

export function ImageGrid({
  items,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: Props) {
  const gridColumns = useFilterStore((s) => s.gridColumns);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))` }}
      >
        {items.map((item) => (
          <ImageItem key={item.hash} item={item} />
        ))}
      </div>
      <div ref={sentinelRef} className="h-10 mt-2" />
      {isFetchingNextPage && (
        <div className="py-4 text-center text-sm text-gray-500">
          Loading more...
        </div>
      )}
    </div>
  );
}
