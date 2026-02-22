import React from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInterviewEvents } from "@/lib/hooks/use-interview-events";
import type { InterviewSseEnvelope } from "@/lib/api/types";

type ConnectArgs = {
  sessionId: string;
  lastEventId?: string;
};

const connectMock = vi.fn();

vi.mock("@/lib/api/interview-sse", () => ({
  connectInterviewSse: (...args: unknown[]) => connectMock(...args)
}));

describe("useInterviewEvents", () => {
  beforeEach(() => {
    connectMock.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("handles connected/heartbeat/status and resumes with Last-Event-ID", async () => {
    const calls: ConnectArgs[] = [];

    connectMock.mockImplementationOnce(async (options: ConnectArgs, onEvent: (evt: InterviewSseEnvelope) => void) => {
      calls.push(options);
      onEvent({
        id: "1",
        event: "connected",
        data: {
          session_id: options.sessionId,
          trace_id: "trace-a",
          connected_at: "2026-01-01T00:00:00",
          resumed: false
        }
      });
      onEvent({
        id: "2",
        event: "status",
        data: {
          session_id: options.sessionId,
          trace_id: "trace-a",
          status: "processing"
        }
      });
      return {
        close: vi.fn(),
        done: Promise.resolve()
      };
    });

    connectMock.mockImplementationOnce(async (options: ConnectArgs, onEvent: (evt: InterviewSseEnvelope) => void) => {
      calls.push(options);
      onEvent({
        id: "-1",
        event: "heartbeat",
        data: {
          session_id: options.sessionId,
          trace_id: "trace-a",
          at: "2026-01-01T00:00:01"
        }
      });
      onEvent({
        id: "3",
        event: "completed",
        data: {
          session_id: options.sessionId,
          trace_id: "trace-a",
          status: "idle_timeout",
          idle_seconds: 310,
          at: "2026-01-01T00:05:10"
        }
      });
      return {
        close: vi.fn(),
        done: Promise.resolve()
      };
    });

    const { result } = renderHook(() => useInterviewEvents("sess-1"), {
      wrapper: ({ children }: { children: React.ReactNode }) => <>{children}</>
    });

    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    expect(calls[0]).toEqual({ sessionId: "sess-1", lastEventId: undefined });
    expect(calls[1]).toEqual({ sessionId: "sess-1", lastEventId: "2" });
    expect(result.current.lastEventId).toBe("3");
    expect(result.current.completedEvent?.status).toBe("idle_timeout");
    expect(result.current.connectionState).toBe("closed");
  });

  it("maps SSE error event into normalized error fields", async () => {
    connectMock.mockImplementationOnce(async (options: ConnectArgs, onEvent: (evt: InterviewSseEnvelope) => void) => {
      onEvent({
        id: "1",
        event: "connected",
        data: {
          session_id: options.sessionId,
          trace_id: "trace-b",
          connected_at: "2026-01-01T00:00:00",
          resumed: false
        }
      });
      onEvent({
        id: "2",
        event: "error",
        data: {
          session_id: options.sessionId,
          error_code: "INTERVIEW_MESSAGE_FAILED",
          error_message: "boom",
          retryable: false,
          trace_id: "trace-b"
        }
      });
      return {
        close: vi.fn(),
        done: Promise.resolve()
      };
    });

    const { result } = renderHook(() => useInterviewEvents("sess-2"), {
      wrapper: ({ children }: { children: React.ReactNode }) => <>{children}</>
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.error).toMatchObject({
      code: "INTERVIEW_MESSAGE_FAILED",
      message: "boom",
      retryable: false,
      traceId: "trace-b"
    });
  });

  it("treats aborted stream as closed without surfacing UNKNOWN_ERROR", async () => {
    connectMock.mockImplementationOnce(async () => {
      return {
        close: vi.fn(),
        done: Promise.reject(new DOMException("BodyStreamBuffer was aborted", "AbortError"))
      };
    });

    const { result } = renderHook(() => useInterviewEvents("sess-abort"), {
      wrapper: ({ children }: { children: React.ReactNode }) => <>{children}</>
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.connectionState).toBe("closed");
    expect(result.current.error).toBeNull();
  });
});
