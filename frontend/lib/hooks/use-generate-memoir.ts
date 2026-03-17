"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useMutationState, useQuery } from "@tanstack/react-query";
import { ApiRequestError } from "@/lib/api/client";
import { generateMemoir, getSavedMemoir } from "@/lib/api/generate";
import { useGenerationStatus } from "@/lib/hooks/use-generation-status";
import { useWorkspaceContext } from "@/lib/workspace/context";
import type { MemoirGenerateData, MemoirGenerateRequest, NormalizedApiError } from "@/lib/api/types";

function pendingStorageKey(username: string | null | undefined): string | null {
  return username ? `generate_pending_memoir_${username}` : null;
}

function readPendingFlag(key: string | null): boolean {
  if (!key || typeof window === "undefined") return false;
  try {
    return sessionStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writePendingFlag(key: string | null, active: boolean) {
  if (!key || typeof window === "undefined") return;
  try {
    if (active) {
      sessionStorage.setItem(key, "1");
    } else {
      sessionStorage.removeItem(key);
    }
  } catch {
    // ignore storage errors
  }
}

export function useGenerateMemoir() {
  const { username } = useWorkspaceContext();
  const generationStatusQuery = useGenerationStatus();
  const [generatedData, setGeneratedData] = useState<MemoirGenerateData | null>(null);
  const [persistedPending, setPersistedPending] = useState<boolean>(() => readPendingFlag(pendingStorageKey(username)));
  const prevServerPendingRef = useRef(false);
  const storageKey = pendingStorageKey(username);

  const setPendingFlag = useCallback((active: boolean) => {
    setPersistedPending(active);
    writePendingFlag(storageKey, active);
  }, [storageKey]);

  useEffect(() => {
    setPersistedPending(readPendingFlag(storageKey));
  }, [storageKey]);

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
    onMutate: () => {
      setPendingFlag(true);
    },
    onSuccess: (result) => {
      setGeneratedData(result);
    },
    onSettled: () => {
      setPendingFlag(false);
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
  const serverPending = generationStatusQuery.data?.memoir_active ?? false;
  const storagePending = readPendingFlag(storageKey);
  const hasPendingHint = persistedPending || storagePending;
  const waitingForInitialStatus =
    Boolean(username) &&
    !generationStatusQuery.isFetched &&
    generationStatusQuery.fetchStatus === "fetching";
  const restorePendingWhileChecking = hasPendingHint && !generationStatusQuery.isFetched;
  const isPending = mutation.isPending || isGloballyPending || serverPending || restorePendingWhileChecking;
  const isLocked = isPending || waitingForInitialStatus;

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
  const visibleError =
    normalizedError?.code === "GENERATION_ALREADY_RUNNING" && isLocked
      ? null
      : normalizedError;

  // Use mutation result if available, otherwise fall back to global cache, then saved data
  const data = generatedData ?? mutation.data ?? cachedMutationData ?? (savedQuery.data ?? null);

  useEffect(() => {
    if (!generationStatusQuery.isFetched) return;
    if (!serverPending) {
      setPendingFlag(false);
    }
    if (prevServerPendingRef.current && !serverPending) {
      void savedQuery.refetch();
    }
    prevServerPendingRef.current = serverPending;
  }, [generationStatusQuery.isFetched, savedQuery, serverPending, setPendingFlag]);

  return {
    ...mutation,
    isPending,
    isLocked,
    data,
    normalizedError: visibleError,
    canRetry: Boolean(visibleError?.retryable)
  };
}
