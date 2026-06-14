import type { CacheItem } from "../types";
import { FileItem } from "./FileItem";

interface Props {
  items: CacheItem[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
}

export function FileList({
  items,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: Props) {
  return (
    <div className="flex-1 overflow-y-auto">
      {items.map((item) => (
        <FileItem key={item.hash} item={item} />
      ))}
      {hasNextPage && (
        <div className="py-4 text-center">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-sm rounded border border-gray-300 disabled:opacity-50"
          >
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
