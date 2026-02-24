"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getApiBaseUrl, getAuthHeaders, normalizeUnknownError } from "@/lib/api/client";
import { triggerReprocess, cancelStructuring } from "@/lib/api/knowledge";
import { knowledgeQueryKeys } from "@/lib/query-keys";

export type StructuringStage = "读取文件" | "提取事件" | "向量化" | "完成" | null;

export type UseKnowledgeStructuringResult = {
  isProcessing: boolean;
  stage: StructuringStage;
  error: string | null;
  trigger: () => Promise<void>;
  cancel: () => Promise<void>;
};

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

export function useKnowledgeStructuring(materialId: string): UseKnowledgeStructuringResult {
  const [isProcessing, setIsProcessing] = useState(false);
  const [stage, setStage] = useState<StructuringStage>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  // Cleanup SSE connection on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const invalidateKnowledgeQueries = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.materials });
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.events });
    void queryClient.invalidateQueries({ queryKey: knowledgeQueryKeys.profiles });
  }, [queryClient]);

  const cancel = useCallback(async () => {
    // Abort the local SSE reader immediately
    abortRef.current?.abort();
    abortRef.current = null;

    // Tell the backend to stop the task and reset to pending
    try {
      await cancelStructuring(materialId);
    } catch {
      // Best-effort — backend may already be done
    }

    setIsProcessing(false);
    setStage(null);
    setError(null);
    invalidateKnowledgeQueries();
  }, [invalidateKnowledgeQueries, materialId]);

  const trigger = useCallback(async () => {
    if (isProcessing) return;

    setIsProcessing(true);
    setStage("读取文件");
    setError(null);

    try {
      await triggerReprocess(materialId);
    } catch (err) {
      const normalized = normalizeUnknownError(err, "触发结构化失败");
      setError(normalized.message);
      setIsProcessing(false);
      setStage(null);
      return;
    }

    // Open SSE stream via fetch (supports auth headers)
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(
        `${getApiBaseUrl()}/knowledge/materials/${materialId}/events`,
        {
          method: "GET",
          headers: { Accept: "text/event-stream", ...getAuthHeaders() },
          signal: controller.signal,
        }
      );

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
            const label = payload.label as StructuringStage;
            if (label) setStage(label);
          } else if (eventName === "completed") {
            setStage("完成");
            setIsProcessing(false);
            invalidateKnowledgeQueries();
            reader.releaseLock();
            return;
          } else if (eventName === "error") {
            const msg = (payload.message as string) || "结构化失败";
            setError(msg);
            setIsProcessing(false);
            setStage(null);
            invalidateKnowledgeQueries();
            reader.releaseLock();
            return;
          }
        }
      }

      // Stream ended without explicit completed event
      setIsProcessing(false);
      invalidateKnowledgeQueries();
    } catch (err) {
      if (isAbortLikeError(err)) {
        // Aborted via cancel() — state already reset there, nothing to do here
        return;
      }
      const normalized = normalizeUnknownError(err, "结构化连接中断");
      setError(normalized.message);
      setIsProcessing(false);
      setStage(null);
      invalidateKnowledgeQueries();
    }
  }, [invalidateKnowledgeQueries, isProcessing, materialId]);

  return { isProcessing, stage, error, trigger, cancel };
}
