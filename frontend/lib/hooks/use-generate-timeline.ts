"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiRequestError, normalizeUnknownError } from "@/lib/api/client";
import { generateTimeline } from "@/lib/api/timeline";
import type { NormalizedApiError, TimelineGenerateData, TimelineGenerateRequest } from "@/lib/api/types";

export type GenerateTimelinePhase = "idle" | "pending" | "success" | "error";

export function useGenerateTimeline() {
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const requestSeqRef = useRef(0);
  const [lastRequest, setLastRequest] = useState<TimelineGenerateRequest | null>(null);
  const [data, setData] = useState<TimelineGenerateData | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const mutation = useMutation<TimelineGenerateData, Error, TimelineGenerateRequest, { requestId: number }>({
    mutationFn: async (payload) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      return generateTimeline(payload, controller.signal);
    },
    retry: false,
    onMutate: (payload) => {
      requestSeqRef.current += 1;
      setLastRequest(payload);
      setError(null);
      return { requestId: requestSeqRef.current };
    },
    onSuccess: (result, _, context) => {
      if (context?.requestId !== requestSeqRef.current) {
        return;
      }
      setData(result);
    },
    onError: (raw, _, context) => {
      if (context?.requestId !== requestSeqRef.current) {
        return;
      }
      const normalized =
        raw instanceof ApiRequestError
          ? raw.normalized
          : normalizeUnknownError(raw, "时间线生成失败");
      if (normalized.code !== "REQUEST_ABORTED") {
        setError(normalized);
      }
    }
  });

  const submit = useCallback(
    async (payload: TimelineGenerateRequest): Promise<TimelineGenerateData | null> => {
      if (mutation.isPending || inFlightRef.current) {
        return null;
      }

      try {
        inFlightRef.current = true;
        return await mutation.mutateAsync(payload);
      } catch {
        return null;
      } finally {
        inFlightRef.current = false;
      }
    },
    [mutation]
  );

  const retry = useCallback(async () => {
    if (!lastRequest || !error?.retryable || mutation.isPending) {
      return null;
    }
    return submit(lastRequest);
  }, [error?.retryable, lastRequest, mutation.isPending, submit]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setData(null);
    setError(null);
    mutation.reset();
  }, [mutation]);

  const phase: GenerateTimelinePhase = mutation.isPending
    ? "pending"
    : error
      ? "error"
      : data
        ? "success"
        : "idle";

  return {
    phase,
    data,
    error,
    isPending: mutation.isPending,
    canRetry: Boolean(error?.retryable && lastRequest),
    lastRequest,
    submit,
    retry,
    reset
  };
}
