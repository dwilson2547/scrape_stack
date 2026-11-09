import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Sidebar } from "./components/Sidebar";
import { FilterBar } from "./components/FilterBar";
import { BrowsePane } from "./components/BrowsePane";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex h-screen bg-gray-50 text-gray-900 overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <FilterBar />
          <BrowsePane />
        </div>
      </div>
    </QueryClientProvider>
  );
}
