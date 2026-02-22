"use client";

import { useMutation } from "@tanstack/react-query";
import { ApiRequestError } from "@/lib/api/client";
import { generateMemoir } from "@/lib/api/memoir";
import type { MemoirGenerateData, MemoirGenerateRequest, NormalizedApiError } from "@/lib/api/types";

export type GenerateState = {
  data: MemoirGenerateData | null;
  error: NormalizedApiError | null;
};

export function useGenerateMemoir() {
  const mutation = useMutation<MemoirGenerateData, Error, MemoirGenerateRequest>({
    mutationFn: generateMemoir,
    retry: false
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

  return {
    ...mutation,
    normalizedError,
    canRetry: Boolean(normalizedError?.retryable)
  };
}
