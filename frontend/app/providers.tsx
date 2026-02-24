"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { WorkspaceProvider } from "@/lib/workspace/context";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() =>
    new QueryClient({
      defaultOptions: {
        mutations: { retry: false },
        queries: { retry: false }
      }
    })
  );

  return (
    <QueryClientProvider client={client}>
      <WorkspaceProvider>{children}</WorkspaceProvider>
    </QueryClientProvider>
  );
}
