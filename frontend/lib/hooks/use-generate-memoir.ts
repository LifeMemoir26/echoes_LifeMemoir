"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiRequestError } from "@/lib/api/client";
import { generateMemoir, getSavedMemoir } from "@/lib/api/memoir";
import type { MemoirGenerateData, MemoirGenerateRequest, NormalizedApiError } from "@/lib/api/types";

export type GenerateState = {
  data: MemoirGenerateData | null;
  error: NormalizedApiError | null;
};

export function useGenerateMemoir() {
  const [generatedData, setGeneratedData] = useState<MemoirGenerateData | null>(null);

  // Load saved memoir via React Query (cached 5 min in memory)
  const savedQuery = useQuery({
    queryKey: ["memoir-saved"],
    queryFn: ({ signal }) => getSavedMemoir(signal),
    staleTime: 5 * 60 * 1000,
  });

  const mutation = useMutation<MemoirGenerateData, Error, MemoirGenerateRequest>({
    mutationFn: generateMemoir,
    retry: false,
    onSuccess: (result) => {
      setGeneratedData(result);
    },
  });

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

  // Use mutation result if available, otherwise fall back to saved data
  const data = generatedData ?? mutation.data ?? (savedQuery.data ?? null);

  return {
    ...mutation,
    data,
    normalizedError,
    canRetry: Boolean(normalizedError?.retryable)
  };
}
