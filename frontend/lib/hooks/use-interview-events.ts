"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { connectInterviewSse } from "@/lib/api/interview";
import { normalizeInterviewSseError, normalizeUnknownError } from "@/lib/api/client";
import type {
  InterviewSseEnvelope,
  InterviewStreamCompleted,
  InterviewStreamContext,
  InterviewStreamError,
  InterviewStreamStatus,
  NormalizedApiError
} from "@/lib/api/types";

type ConnectionState = "idle" | "connecting" | "ready" | "reconnecting" | "closed" | "fatal";

const RETRY_MS = [1000, 2000, 4000, 8000, 15000] as const;

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

export function useInterviewEvents(sessionId: string | null) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [events, setEvents] = useState<InterviewSseEnvelope[]>([]);
  const [statusEvent, setStatusEvent] = useState<InterviewStreamStatus | null>(null);
  const [contextEvent, setContextEvent] = useState<InterviewStreamContext | null>(null);
  const [completedEvent, setCompletedEvent] = useState<InterviewStreamCompleted | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [lastEventId, setLastEventId] = useState<string | null>(null);

  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldStopRef = useRef(false);
  const streamCloserRef = useRef<(() => void) | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    streamCloserRef.current?.();
    streamCloserRef.current = null;
  }, []);

  const handleEvent = useCallback(
    (incoming: InterviewSseEnvelope) => {
      if (incoming.id && incoming.id !== "-1") {
        lastEventIdRef.current = incoming.id;
        setLastEventId(incoming.id);
      }

      setEvents((prev) => [...prev, incoming].slice(-200));

      if (incoming.event === "status") {
        const status = incoming.data as InterviewStreamStatus;
        setStatusEvent(status);
      }

      if (incoming.event === "connected") {
        setConnectionState("ready");
      }

      if (incoming.event === "context") {
        const context = incoming.data as InterviewStreamContext;
        setContextEvent(context);
      }

      if (incoming.event === "completed") {
        const completed = incoming.data as InterviewStreamCompleted;
        setCompletedEvent(completed);
        if (completed.status === "session_closed" || completed.status === "idle_timeout") {
          shouldStopRef.current = true;
          cleanup();
          setConnectionState("closed");
        }
      }

      if (incoming.event === "error") {
        const eventError = incoming.data as InterviewStreamError;
        setError(normalizeInterviewSseError(eventError));
      }
    },
    [cleanup]
  );

  const connect = useCallback(async () => {
    if (!sessionId || shouldStopRef.current) {
      return;
    }

    try {
      const nextState = reconnectAttemptRef.current > 0 ? "reconnecting" : "connecting";
      setConnectionState(nextState);
      setError(null);
      const handle = await connectInterviewSse(
        {
          sessionId,
          lastEventId: lastEventIdRef.current ?? undefined
        },
        handleEvent
      );
      streamCloserRef.current = handle.close;
      if (shouldStopRef.current) {
        handle.close();
        setConnectionState("closed");
        return;
      }
      reconnectAttemptRef.current = 0;

      await handle.done;
      if (shouldStopRef.current) {
        return;
      }

      setConnectionState("reconnecting");
      const delay = RETRY_MS[Math.min(reconnectAttemptRef.current, RETRY_MS.length - 1)];
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        void connect();
      }, delay);
    } catch (raw) {
      if (shouldStopRef.current || isAbortLikeError(raw)) {
        setConnectionState("closed");
        return;
      }

      const normalized = normalizeUnknownError(raw, "SSE 连接失败");
      setError(normalized);

      if (normalized.code === "SESSION_NOT_FOUND" || !normalized.retryable) {
        setConnectionState("fatal");
        shouldStopRef.current = true;
        return;
      }

      setConnectionState("reconnecting");
      const delay = RETRY_MS[Math.min(reconnectAttemptRef.current, RETRY_MS.length - 1)];
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        void connect();
      }, delay);
    }
  }, [handleEvent, sessionId]);

  const reconnectNow = useCallback(() => {
    if (!sessionId) {
      return;
    }
    shouldStopRef.current = false;
    reconnectAttemptRef.current = 0;
    cleanup();
    void connect();
  }, [cleanup, connect, sessionId]);

  const disconnect = useCallback(() => {
    shouldStopRef.current = true;
    cleanup();
    setConnectionState("closed");
  }, [cleanup]);

  useEffect(() => {
    cleanup();
    shouldStopRef.current = false;
    reconnectAttemptRef.current = 0;

    setEvents([]);
    setStatusEvent(null);
    setContextEvent(null);
    setCompletedEvent(null);
    setError(null);
    setLastEventId(null);
    lastEventIdRef.current = null;

    if (!sessionId) {
      setConnectionState("idle");
      return;
    }

    void connect();
    return () => {
      shouldStopRef.current = true;
      cleanup();
    };
  }, [cleanup, connect, sessionId]);

  const summary = useMemo(
    () => ({
      eventCount: events.length,
      lastStatus: statusEvent?.status ?? completedEvent?.status ?? null,
      lastTraceId: statusEvent?.trace_id ?? contextEvent?.trace_id ?? completedEvent?.trace_id ?? null
    }),
    [completedEvent?.status, completedEvent?.trace_id, contextEvent?.trace_id, events.length, statusEvent?.status, statusEvent?.trace_id]
  );

  return {
    connectionState,
    events,
    statusEvent,
    contextEvent,
    completedEvent,
    error,
    lastEventId,
    summary,
    reconnectNow,
    disconnect
  };
}
