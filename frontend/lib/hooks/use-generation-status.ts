"use client";

import { useQuery } from "@tanstack/react-query";

import { getGenerationStatus } from "@/lib/api/generate";
import { useWorkspaceContext } from "@/lib/workspace/context";

export function useGenerationStatus() {
  const { username } = useWorkspaceContext();

  return useQuery({
    queryKey: ["generate-status", username],
    queryFn: ({ signal }) => getGenerationStatus(signal),
    enabled: Boolean(username),
    staleTime: 0,
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
  });
}
