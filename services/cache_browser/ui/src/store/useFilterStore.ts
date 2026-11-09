import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CacheType } from "../types";

interface FilterState {
  cacheType: CacheType;
  bucket: string | null;
  prefix: string | null;
  clientName: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  q: string;
  gridColumns: number;
  setCacheType: (t: CacheType) => void;
  setBucket: (b: string | null) => void;
  setPrefix: (p: string | null) => void;
  setClientName: (c: string | null) => void;
  setDateFrom: (d: string | null) => void;
  setDateTo: (d: string | null) => void;
  setQ: (q: string) => void;
  setGridColumns: (n: number) => void;
}

export const useFilterStore = create<FilterState>()(
  persist(
    (set) => ({
      cacheType: "web",
      bucket: null,
      prefix: null,
      clientName: null,
      dateFrom: null,
      dateTo: null,
      q: "",
      gridColumns: 4,
      setCacheType: (cacheType) =>
        set({ cacheType, bucket: null, prefix: null }),
      setBucket: (bucket) => set({ bucket, prefix: null }),
      setPrefix: (prefix) => set({ prefix }),
      setClientName: (clientName) => set({ clientName }),
      setDateFrom: (dateFrom) => set({ dateFrom }),
      setDateTo: (dateTo) => set({ dateTo }),
      setQ: (q) => set({ q }),
      setGridColumns: (gridColumns) => set({ gridColumns }),
    }),
    {
      name: "cache-browser-filters",
    }
  )
);
