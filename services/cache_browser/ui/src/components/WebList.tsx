import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { CacheItem } from "../types";
import { WebItem } from "./WebItem";

interface Props {
  items: CacheItem[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}

export function WebList({
  items,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const lastVirtualItem = virtualItems[virtualItems.length - 1];

  useEffect(() => {
    if (!lastVirtualItem) return;
    if (
      lastVirtualItem.index >= items.length - 1 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [lastVirtualItem?.index, items.length, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div ref={parentRef} className="flex-1 overflow-y-auto">
      <div
        style={{
          height: virtualizer.getTotalSize(),
          width: "100%",
          position: "relative",
        }}
      >
        {virtualItems.map((vItem) => (
          <div
            key={vItem.key}
            data-index={vItem.index}
            ref={virtualizer.measureElement}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${vItem.start}px)`,
            }}
          >
            <WebItem item={items[vItem.index]} />
          </div>
        ))}
      </div>
      {isFetchingNextPage && (
        <div className="py-4 text-center text-sm text-gray-500">
          Loading more...
        </div>
      )}
    </div>
  );
}
