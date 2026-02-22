"use client";

import { useCallback, useMemo, useState } from "react";
import { normalizeUnknownError } from "@/lib/api/client";
import {
  closeInterviewSession,
  createInterviewSession,
  flushInterviewSession,
  sendInterviewMessage
} from "@/lib/api/interview";
import type { NormalizedApiError, SessionActionData, SessionCreateData } from "@/lib/api/types";

export type InterviewCommandState =
  | "idle"
  | "creating_session"
  | "connected"
  | "processing"
  | "flushing"
  | "ready_for_next_turn"
  | "closed"
  | "idle_timeout"
  | "session_not_found"
  | "session_conflict"
  | "error";

export function useInterviewSession() {
  const [session, setSession] = useState<SessionCreateData | null>(null);
  const [state, setState] = useState<InterviewCommandState>("idle");
  const [lastAction, setLastAction] = useState<SessionActionData | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [recoverableSessionId, setRecoverableSessionId] = useState<string | null>(null);
  const [inFlightCommand, setInFlightCommand] = useState<"create" | "send" | "flush" | "close" | null>(null);

  // Unlock as soon as the HTTP call returns — don't block on SSE-driven state.
  // isProcessing visual indicators still reflect SSE "processing"/"flushing" states.
  const canSubmitCommand = !inFlightCommand;

  const create = useCallback(async (username: string) => {
    if (inFlightCommand) {
      return null;
    }

    setInFlightCommand("create");
    setState("creating_session");
    setError(null);

    try {
      const next = await createInterviewSession({ username });
      setSession(next);
      setState("connected");
      setRecoverableSessionId(null);
      return next;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "创建会话失败");
      setError(normalized);
      if (normalized.code === "SESSION_CONFLICT") {
        const existingSessionId = normalized.details?.existing_session_id;
        setRecoverableSessionId(typeof existingSessionId === "string" ? existingSessionId : null);
        setState("session_conflict");
      } else {
        setRecoverableSessionId(null);
        setState("error");
      }
      return null;
    } finally {
      setInFlightCommand(null);
    }
  }, [inFlightCommand]);

  const send = useCallback(async (content: string) => {
    if (!session?.session_id || !canSubmitCommand) {
      return null;
    }

    setInFlightCommand("send");
    setState("processing");
    setError(null);

    try {
      const action = await sendInterviewMessage(session.session_id, {
        speaker: "user",
        content,
        timestamp: Date.now() / 1000
      });
      setLastAction(action);
      return action;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "发送采访消息失败");
      setError(normalized);
      if (normalized.code === "SESSION_NOT_FOUND") {
        setState("session_not_found");
      } else {
        setState("error");
      }
      return null;
    } finally {
      setInFlightCommand(null);
    }
  }, [canSubmitCommand, session?.session_id]);

  const flush = useCallback(async () => {
    if (!session?.session_id || !canSubmitCommand) {
      return null;
    }

    setInFlightCommand("flush");
    setState("flushing");
    setError(null);

    try {
      const action = await flushInterviewSession(session.session_id);
      setLastAction(action);
      return action;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "刷新采访上下文失败");
      setError(normalized);
      if (normalized.code === "SESSION_NOT_FOUND") {
        setState("session_not_found");
      } else {
        setState("error");
      }
      return null;
    } finally {
      setInFlightCommand(null);
    }
  }, [canSubmitCommand, session?.session_id]);

  const close = useCallback(async () => {
    if (!session?.session_id || inFlightCommand) {
      return null;
    }

    setInFlightCommand("close");
    setError(null);

    try {
      const action = await closeInterviewSession(session.session_id);
      setLastAction(action);
      setState("closed");
      setRecoverableSessionId(null);
      return action;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "关闭会话失败");
      setError(normalized);
      if (normalized.code === "SESSION_NOT_FOUND") {
        setState("session_not_found");
      } else {
        setState("error");
      }
      return null;
    } finally {
      setInFlightCommand(null);
    }
  }, [inFlightCommand, session?.session_id]);

  const recoverFromConflict = useCallback((sessionId: string, username: string) => {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      return;
    }

    setSession({
      session_id: normalizedSessionId,
      thread_id: "",
      username: username.trim(),
      created_at: new Date().toISOString()
    });
    setError(null);
    setState("connected");
    setRecoverableSessionId(normalizedSessionId);
  }, []);

  const syncFromServerEvent = useCallback((serverStatus: string | null | undefined, eventSessionId?: string | null) => {
    if (!serverStatus) {
      return;
    }

    if (eventSessionId && session?.session_id && eventSessionId !== session.session_id) {
      return;
    }

    if (serverStatus === "processing") {
      setState("processing");
      return;
    }

    if (serverStatus === "flushing") {
      setState("flushing");
      return;
    }

    if (serverStatus === "message_processed" || serverStatus === "flush_completed" || serverStatus === "created") {
      setState("ready_for_next_turn");
      return;
    }

    if (serverStatus === "session_closed") {
      setState("closed");
      return;
    }

    if (serverStatus === "idle_timeout") {
      setState("idle_timeout");
    }
  }, [session?.session_id]);

  const summary = useMemo(() => {
    return {
      sessionId: session?.session_id ?? null,
      threadId: session?.thread_id ?? null,
      username: session?.username ?? null,
      state,
      traceId: lastAction?.trace_id ?? session?.thread_id ?? null
    };
  }, [lastAction?.trace_id, session?.session_id, session?.thread_id, session?.username, state]);

  return {
    session,
    state,
    summary,
    error,
    lastAction,
    recoverableSessionId,
    inFlightCommand,
    canSubmitCommand,
    create,
    send,
    flush,
    close,
    recoverFromConflict,
    syncFromServerEvent
  };
}
