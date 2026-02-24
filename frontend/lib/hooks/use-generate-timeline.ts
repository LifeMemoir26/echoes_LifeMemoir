"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useMutationState, useQuery } from "@tanstack/react-query";
import { ApiRequestError, normalizeUnknownError } from "@/lib/api/client";
import { generateTimeline, getSavedTimeline } from "@/lib/api/timeline";
import { useWorkspaceContext } from "@/lib/workspace/context";
import type { NormalizedApiError, TimelineGenerateData, TimelineGenerateRequest } from "@/lib/api/types";

export type GenerateTimelinePhase = "idle" | "pending" | "success" | "error";

export function useGenerateTimeline() {
  const { timelineCache, setTimelineCache } = useWorkspaceContext();

  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const requestSeqRef = useRef(0);
  const cacheAppliedRef = useRef(false);

  // Initialise from cache (only on first mount — may be null if context hasn't
  // hydrated from sessionStorage yet; the effect below handles the late arrival)
  const [lastRequest, setLastRequest] = useState<TimelineGenerateRequest | null>(
    () => timelineCache?.lastRequest ?? null
  );
  const [data, setData] = useState<TimelineGenerateData | null>(
    () => (timelineCache?.phase === "success" ? timelineCache.data : null)
  );
  const [error, setError] = useState<NormalizedApiError | null>(
    () => (timelineCache?.phase === "error" ? timelineCache.error : null)
  );

  // Mark cache as already applied if the lazy initializers did pick it up
  if (timelineCache && !cacheAppliedRef.current && (data || error)) {
    cacheAppliedRef.current = true;
  }

  const mutation = useMutation<TimelineGenerateData, Error, TimelineGenerateRequest, { requestId: number }>({
    mutationKey: ["generate-timeline"],
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

  // ── Survive navigation: observe global MutationCache ──────────────────────
  const globalPending = useMutationState({
    filters: { mutationKey: ["generate-timeline"], status: "pending" },
    select: () => true as const,
  });
  const globalSuccessData = useMutationState({
    filters: { mutationKey: ["generate-timeline"], status: "success" },
    select: (m) => m.state.data as TimelineGenerateData | undefined,
  });
  const isGloballyPending = !mutation.isPending && globalPending.length > 0;

  // Pick up data from a mutation that completed while we were on another page
  useEffect(() => {
    if (data || mutation.isPending) return;
    const latest = globalSuccessData[globalSuccessData.length - 1];
    if (latest) setData(latest);
  }, [globalSuccessData, data, mutation.isPending]);

  const phase: GenerateTimelinePhase = (mutation.isPending || isGloballyPending)
    ? "pending"
    : error
      ? "error"
      : data
        ? "success"
        : "idle";

  // ── Restore from context cache when it arrives after mount ──────────────
  useEffect(() => {
    if (cacheAppliedRef.current || !timelineCache) return;
    cacheAppliedRef.current = true;

    if (timelineCache.phase === "success" && timelineCache.data) {
      setData(timelineCache.data);
      setLastRequest(timelineCache.lastRequest);
    } else if (timelineCache.phase === "error") {
      setError(timelineCache.error);
      setLastRequest(timelineCache.lastRequest);
    }
  }, [timelineCache]);

  // ── Load saved timeline from disk via React Query (cached 5 min) ────────
  const savedQuery = useQuery({
    queryKey: ["timeline-saved"],
    queryFn: ({ signal }) => getSavedTimeline(signal),
    staleTime: 5 * 60 * 1000,
    enabled: !data && !error,
  });

  // Apply saved data once available
  useEffect(() => {
    if (data || error) return; // already have data from cache or generation
    if (savedQuery.data && savedQuery.data.timeline.length > 0) {
      setData(savedQuery.data);
    }
  }, [savedQuery.data, data, error]);

  // ── Persist state to WorkspaceContext on each change ─────────────────────
  useEffect(() => {
    // Don't overwrite a valid restored cache with idle state on mount
    if (phase === "idle" && !data && !error && !lastRequest) return;
    setTimelineCache({
      phase,
      data,
      error,
      lastRequest,
      savedAt: Date.now(),
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, data, error, lastRequest]);

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
    setTimelineCache(null);
  }, [mutation, setTimelineCache]);

  return {
    phase,
    data,
    error,
    isPending: mutation.isPending || isGloballyPending,
    canRetry: Boolean(error?.retryable && lastRequest),
    lastRequest,
    submit,
    retry,
    reset
  };
}
