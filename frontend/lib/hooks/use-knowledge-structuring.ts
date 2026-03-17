"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getApiBaseUrl, normalizeUnknownError } from "@/lib/api/client";
import { triggerReprocess, cancelStructuring } from "@/lib/api/knowledge";
import { knowledgeQueryKeys } from "@/lib/query-keys";

export type StructuringStage =
  | "文件读取"
  | "知识提取"
  | "向量化存储"
  | "完成"
  | null;

export type UseKnowledgeStructuringResult = {
  isProcessing: boolean;
  stage: StructuringStage;
  error: string | null;
  trigger: () => Promise<void>;
  cancel: () => Promise<void>;
};

type StructuringSnapshot = {
  isProcessing: boolean;
  stage: StructuringStage;
  error: string | null;
};

const STAGE_KEY_TO_LABEL: Record<string, Exclude<StructuringStage, null>> = {
  ingest: "文件读取",
  extract: "知识提取",
  vectorize: "向量化存储",
  completed: "完成",
};

const snapshots = new Map<string, StructuringSnapshot>();
const controllers = new Map<string, AbortController>();
const subscribers = new Map<string, Set<(state: StructuringSnapshot) => void>>();

function defaultSnapshot(): StructuringSnapshot {
  return { isProcessing: false, stage: null, error: null };
}

function getSnapshot(materialId: string): StructuringSnapshot {
  return snapshots.get(materialId) ?? defaultSnapshot();
}

function setSnapshot(materialId: string, patch: Partial<StructuringSnapshot>) {
  const current = getSnapshot(materialId);
  const next = { ...current, ...patch };
  snapshots.set(materialId, next);
  const listeners = subscribers.get(materialId);
  if (!listeners) return;
  for (const listener of listeners) {
    listener(next);
  }
}

function subscribe(materialId: string, listener: (state: StructuringSnapshot) => void): () => void {
  const set = subscribers.get(materialId) ?? new Set<(state: StructuringSnapshot) => void>();
  set.add(listener);
  subscribers.set(materialId, set);

  listener(getSnapshot(materialId));

  return () => {
    const curr = subscribers.get(materialId);
    if (!curr) return;
    curr.delete(listener);
    if (curr.size === 0) {
      subscribers.delete(materialId);
    }
  };
}

function isAbortLikeError(raw: unknown): boolean {
  if (!raw || typeof raw !== "object") {
    return false;
  }

  const name = "name" in raw ? String((raw as { name?: unknown }).name ?? "") : "";
  const message = "message" in raw ? String((raw as { message?: unknown }).message ?? "") : "";

  if (name === "AbortError") {
    return true;
  }

  return /aborted|aborterror|bodystreambuffer was aborted/i.test(`${name} ${message}`);
}

function resolveStage(payload: Record<string, unknown>): StructuringStage {
  const byStageKey = typeof payload.stage === "string" ? STAGE_KEY_TO_LABEL[payload.stage] : undefined;
  if (byStageKey) return byStageKey;

  const byLabel = typeof payload.label === "string" ? payload.label : null;
  if (byLabel === null) return null;

  return (Object.values(STAGE_KEY_TO_LABEL).includes(byLabel as Exclude<StructuringStage, null>)
    ? byLabel
    : null) as StructuringStage;
}

async function openSseStream(materialId: string, invalidate: () => void) {
  if (controllers.has(materialId)) return;

  const controller = new AbortController();
  controllers.set(materialId, controller);

  try {
    const response = await fetch(`${getApiBaseUrl()}/knowledge/materials/${materialId}/events`, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
      credentials: "include",
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`SSE 连接失败（HTTP ${response.status}）`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        const lines = chunk.split(/\r?\n/);
        let eventName = "message";
        const dataParts: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataParts.push(line.slice(5).trim());
        }

        if (!dataParts.length) continue;

        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(dataParts.join("\n"));
        } catch {
          continue;
        }

        if (eventName === "status") {
          const stage = resolveStage(payload);
          if (stage) setSnapshot(materialId, { stage, isProcessing: true, error: null });
        } else if (eventName === "completed") {
          setSnapshot(materialId, { stage: "完成", isProcessing: false, error: null });
          invalidate();
          reader.releaseLock();
          return;
        } else if (eventName === "error") {
          const msg = (payload.message as string) || "结构化失败";
          setSnapshot(materialId, { error: msg, isProcessing: false, stage: null });
          invalidate();
          reader.releaseLock();
          return;
        }
      }
    }

    setSnapshot(materialId, { isProcessing: false, stage: null });
    invalidate();
  } catch (err) {
    if (isAbortLikeError(err)) {
      return;
    }
    const normalized = normalizeUnknownError(err, "结构化连接中断");
    setSnapshot(materialId, { error: normalized.message, isProcessing: false, stage: null });
    invalidate();
  } finally {
    controllers.delete(materialId);
  }
}

export function useKnowledgeStructuring(
  materialId: string,
  serverStatus: "pending" | "processing" | "done" | "failed" = "pending",
): UseKnowledgeStructuringResult {
  const [localState, setLocalState] = useState<StructuringSnapshot>(getSnapshot(materialId));
  const queryClient = useQueryClient();

  const invalidateKnowledgeQueries = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.materials });
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.events });
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.profiles });
  }, [queryClient]);

  useEffect(() => subscribe(materialId, setLocalState), [materialId]);

  useEffect(() => {
    const snap = getSnapshot(materialId);

    if (serverStatus === "processing") {
      if (!snap.isProcessing) {
        setSnapshot(materialId, { isProcessing: true, stage: snap.stage ?? "文件读取", error: null });
      }
      void openSseStream(materialId, invalidateKnowledgeQueries);
      return;
    }

    if (serverStatus === "done") {
      setSnapshot(materialId, { isProcessing: false, stage: "完成", error: null });
      return;
    }

    if (serverStatus === "failed") {
      setSnapshot(materialId, { isProcessing: false, stage: null, error: snap.error ?? "结构化失败" });
    }
  }, [invalidateKnowledgeQueries, materialId, serverStatus]);

  // SSE 丢包或后端快速完成时，轮询 materials 作为兜底，防止进度卡住。
  useEffect(() => {
    if (!localState.isProcessing) return;
    const timer = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.materials });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [localState.isProcessing, queryClient]);

  const trigger = useCallback(async () => {
    const snap = getSnapshot(materialId);
    if (snap.isProcessing) return;

    setSnapshot(materialId, { isProcessing: true, stage: "文件读取", error: null });
    invalidateKnowledgeQueries();

    try {
      await triggerReprocess(materialId);
    } catch (err) {
      const normalized = normalizeUnknownError(err, "触发结构化失败");
      setSnapshot(materialId, { error: normalized.message, isProcessing: false, stage: null });
      return;
    }

    void openSseStream(materialId, invalidateKnowledgeQueries);
  }, [invalidateKnowledgeQueries, materialId]);

  const cancel = useCallback(async () => {
    const controller = controllers.get(materialId);
    controller?.abort();
    controllers.delete(materialId);

    try {
      await cancelStructuring(materialId);
    } catch {
      // Best-effort — backend may already be done
    }

    setSnapshot(materialId, { isProcessing: false, stage: null, error: null });
    invalidateKnowledgeQueries();
  }, [invalidateKnowledgeQueries, materialId]);

  return useMemo(
    () => ({
      isProcessing: localState.isProcessing,
      stage: localState.stage,
      error: localState.error,
      trigger,
      cancel,
    }),
    [localState.error, localState.isProcessing, localState.stage, trigger, cancel],
  );
}
