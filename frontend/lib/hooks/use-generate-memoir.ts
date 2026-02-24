"use client";

import { useEffect, useState } from "react";
import { useMutation, useMutationState, useQuery } from "@tanstack/react-query";
import { ApiRequestError } from "@/lib/api/client";
import { generateMemoir, getSavedMemoir } from "@/lib/api/memoir";
import type { MemoirGenerateData, MemoirGenerateRequest, NormalizedApiError } from "@/lib/api/types";

export function useGenerateMemoir() {
  const [generatedData, setGeneratedData] = useState<MemoirGenerateData | null>(null);

  // Load saved memoir via React Query (cached 5 min in memory)
  const savedQuery = useQuery({
    queryKey: ["memoir-saved"],
    queryFn: ({ signal }) => getSavedMemoir(signal),
    staleTime: 5 * 60 * 1000,
  });

  const mutation = useMutation<MemoirGenerateData, Error, MemoirGenerateRequest>({
    mutationKey: ["generate-memoir"],
    mutationFn: generateMemoir,
    retry: false,
    onSuccess: (result) => {
      setGeneratedData(result);
    },
  });

  // ── Survive navigation: observe global MutationCache ──────────────────────
  const globalPending = useMutationState({
    filters: { mutationKey: ["generate-memoir"], status: "pending" },
    select: () => true as const,
  });
  const globalSuccessData = useMutationState({
    filters: { mutationKey: ["generate-memoir"], status: "success" },
    select: (m) => m.state.data as MemoirGenerateData | undefined,
  });

  const isGloballyPending = globalPending.length > 0;
  const isPending = mutation.isPending || isGloballyPending;

  // Pick up data from a mutation that completed while we were on another page
  const cachedMutationData = globalSuccessData.length > 0
    ? globalSuccessData[globalSuccessData.length - 1] ?? null
    : null;

  const normalizedError: NormalizedApiError | null =
    mutation.error instanceof ApiRequestError
      ? mutation.error.normalized
      : mutation.error
        ? {
            code: /failed to fetch/i.test(mutation.error.message) ? "NETWORK_ERROR" : "UNKNOWN_ERROR",
            message: /failed to fetch/i.test(mutation.error.message)
              ? "无法连接后端服务，请确认后端 8000 端口已启动且前端使用 /api/v1 代理"
              : mutation.error.message,
            retryable: /failed to fetch/i.test(mutation.error.message)
          }
        : null;

  // Use mutation result if available, otherwise fall back to global cache, then saved data
  const data = generatedData ?? mutation.data ?? cachedMutationData ?? (savedQuery.data ?? null);

  return {
    ...mutation,
    isPending,
    data,
    normalizedError,
    canRetry: Boolean(normalizedError?.retryable)
  };
}
