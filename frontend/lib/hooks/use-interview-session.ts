"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { normalizeUnknownError } from "@/lib/api/client";
import {
  closeInterviewSession,
  createInterviewSession,
  flushInterviewSession,
  getActiveInterviewSession,
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

const CREATE_SESSION_TIMEOUT_MS = 8_000;
const ACTIVE_SESSION_POLL_ATTEMPTS = 6;
const ACTIVE_SESSION_POLL_DELAY_MS = 250;

type UseInterviewSessionOptions = {
  initialSessionId?: string | null;
  initialUsername?: string | null;
};

function buildRecoveredSession(
  sessionId: string,
  username: string,
  createdAt?: string,
): SessionCreateData {
  return {
    session_id: sessionId.trim(),
    thread_id: "",
    username: username.trim(),
    created_at: createdAt ?? new Date().toISOString(),
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useInterviewSession(options: UseInterviewSessionOptions = {}) {
  const restoredSession =
    options.initialSessionId && options.initialUsername
      ? buildRecoveredSession(options.initialSessionId, options.initialUsername)
      : null;

  const [session, setSession] = useState<SessionCreateData | null>(restoredSession);
  const [state, setState] = useState<InterviewCommandState>(restoredSession ? "connected" : "idle");
  const [lastAction, setLastAction] = useState<SessionActionData | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [recoverableSessionId, setRecoverableSessionId] = useState<string | null>(null);
  const [inFlightCommand, setInFlightCommand] = useState<"create" | "send" | "flush" | "close" | null>(null);

  // Unlock as soon as the HTTP call returns — don't block on SSE-driven state.
  // isProcessing visual indicators still reflect SSE "processing"/"flushing" states.
  const canSubmitCommand = !inFlightCommand;

  const fetchActiveSession = useCallback(async (attempts: number = 1) => {
    if (!options.initialUsername) {
      return null;
    }

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const active = await getActiveInterviewSession();
        if (!active) {
          if (attempt < attempts - 1) {
            await sleep(ACTIVE_SESSION_POLL_DELAY_MS);
          }
          continue;
        }
        return active;
      } catch {
        if (attempt < attempts - 1) {
          await sleep(ACTIVE_SESSION_POLL_DELAY_MS);
          continue;
        }
      }
    }

    return null;
  }, [options.initialUsername]);

  const syncActiveSession = useCallback(async (attempts: number = 1) => {
    const active = await fetchActiveSession(attempts);
    if (!active) {
      return null;
    }

    setSession(active);
    setState("connected");
    setRecoverableSessionId(active.session_id);
    setError(null);
    return active;
  }, [fetchActiveSession]);

  const waitForNoActiveSession = useCallback(async () => {
    if (!options.initialUsername) {
      return true;
    }

    for (let attempt = 0; attempt < ACTIVE_SESSION_POLL_ATTEMPTS; attempt += 1) {
      const active = await fetchActiveSession();
      if (!active) {
        return true;
      }

      await sleep(ACTIVE_SESSION_POLL_DELAY_MS);
    }

    return false;
  }, [fetchActiveSession, options.initialUsername]);

  useEffect(() => {
    if (!options.initialSessionId || !options.initialUsername) {
      return;
    }
    if (inFlightCommand === "create") {
      return;
    }
    if (state === "closed" || state === "idle_timeout" || state === "session_not_found") {
      return;
    }
    const restoredSessionId = options.initialSessionId;
    const restoredUsername = options.initialUsername;

    if (session?.session_id && session.session_id !== restoredSessionId) {
      return;
    }

    setSession((prev) => {
      if (prev?.session_id === restoredSessionId) {
        return prev;
      }
      return buildRecoveredSession(restoredSessionId, restoredUsername);
    });

    setState((prev) => {
      if (prev === "creating_session" || prev === "processing" || prev === "flushing") {
        return prev;
      }
      if (prev === "closed" || prev === "idle_timeout" || prev === "session_not_found" || prev === "idle") {
        return "connected";
      }
      return prev;
    });
  }, [inFlightCommand, options.initialSessionId, options.initialUsername, session?.session_id, state]);

  useEffect(() => {
    if (state !== "creating_session" || inFlightCommand === "create") {
      return;
    }
    let cancelled = false;

    const timer = setTimeout(() => {
      void (async () => {
        const active = await syncActiveSession(2);
        if (cancelled) {
          return;
        }
        if (active || session?.session_id) {
          setState("connected");
          return;
        }

        if (recoverableSessionId) {
          setState("session_conflict");
          return;
        }

        if (error) {
          setState(error.code === "SESSION_CONFLICT" ? "session_conflict" : "error");
          return;
        }

        setState("idle");
      })();
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [error, inFlightCommand, recoverableSessionId, session?.session_id, state, syncActiveSession]);

  useEffect(() => {
    if (!options.initialUsername || inFlightCommand || session?.session_id) {
      return;
    }
    if (state !== "idle" && state !== "session_conflict") {
      return;
    }

    void syncActiveSession();
  }, [inFlightCommand, options.initialUsername, session?.session_id, state, syncActiveSession]);

  const create = useCallback(async (username: string) => {
    if (inFlightCommand) {
      return null;
    }

    setInFlightCommand("create");
    setState("creating_session");
    setError(null);

    const controller = new AbortController();
    let didTimeout = false;
    const timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, CREATE_SESSION_TIMEOUT_MS);

    try {
      // Some browsers/proxies can leave the create response pending long after
      // the backend has already created the session. Poll the active-session
      // endpoint in parallel so the UI can recover as soon as the server state
      // is visible, instead of blocking on the POST response alone.
      const pollAttempts = Math.max(
        ACTIVE_SESSION_POLL_ATTEMPTS,
        Math.ceil(CREATE_SESSION_TIMEOUT_MS / ACTIVE_SESSION_POLL_DELAY_MS),
      );

      const result = await Promise.race([
        createInterviewSession({ username }, controller.signal).then((session) => ({
          source: "create" as const,
          session,
        })),
        fetchActiveSession(pollAttempts).then((session) =>
          session
            ? {
                source: "active" as const,
                session,
              }
            : null,
        ),
      ]);

      if (!result) {
        didTimeout = true;
        controller.abort();
        throw new Error("CREATE_SESSION_TIMEOUT");
      }

      controller.abort();
      const next = result.session;
      setSession(next);
      setState("connected");
      setRecoverableSessionId(null);
      setError(null);
      return next;
    } catch (raw) {
      const normalized = didTimeout
        ? {
            code: "REQUEST_TIMEOUT",
            message: "创建会话超时，正在尝试恢复已有会话",
            retryable: true,
          }
        : normalizeUnknownError(raw, "创建会话失败");

      const active = await syncActiveSession(ACTIVE_SESSION_POLL_ATTEMPTS);
      if (active) {
        return active;
      }

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
      clearTimeout(timeoutId);
      setInFlightCommand(null);
    }
  }, [fetchActiveSession, inFlightCommand, syncActiveSession]);

  const send = useCallback(async (content: string, speaker: string = "user") => {
    if (!session?.session_id || !canSubmitCommand) {
      return null;
    }

    setInFlightCommand("send");
    setState("processing");
    setError(null);

    try {
      const action = await sendInterviewMessage(session.session_id, {
        speaker,
        content,
        timestamp: Date.now() / 1000
      });
      setLastAction(action);
      return action;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "发送采访消息失败");
      setError(normalized);
      if (normalized.code === "SESSION_NOT_FOUND") {
        setSession(null);
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
        setSession(null);
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
      setSession(null);
      setState("closed");
      setRecoverableSessionId(null);
      return action;
    } catch (raw) {
      const normalized = normalizeUnknownError(raw, "关闭会话失败");
      setError(normalized);
      if (normalized.code === "SESSION_NOT_FOUND") {
        setSession(null);
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

    setSession(buildRecoveredSession(normalizedSessionId, username));
    setError(null);
    setState("connected");
    setRecoverableSessionId(normalizedSessionId);
  }, []);

  /** Close existing conflicting session then create a fresh one. */
  const forceCreate = useCallback(async (username: string) => {
    if (inFlightCommand) return null;

    // Close the old session first (best-effort — ignore errors)
    if (recoverableSessionId) {
      try {
        await closeInterviewSession(recoverableSessionId);
      } catch { /* old session may already be gone */ }
      await waitForNoActiveSession();
    }

    setRecoverableSessionId(null);
    setSession(null);
    setState("idle");
    setError(null);

    return create(username);
  }, [inFlightCommand, recoverableSessionId, create, waitForNoActiveSession]);

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
      setSession(null);
      setState("closed");
      return;
    }

    if (serverStatus === "idle_timeout") {
      setSession(null);
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
    forceCreate,
    send,
    flush,
    close,
    recoverFromConflict,
    syncFromServerEvent
  };
}
