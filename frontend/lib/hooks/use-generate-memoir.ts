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
            code: "UNKNOWN_ERROR",
            message: mutation.error.message,
            retryable: false
          }
        : null;

  return {
    ...mutation,
    normalizedError,
    canRetry: Boolean(normalizedError?.retryable)
  };
}
