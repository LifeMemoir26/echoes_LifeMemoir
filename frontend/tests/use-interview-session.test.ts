import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ApiRequestError } from "@/lib/api/client";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";

vi.mock("@/lib/api/interview", () => ({
  createInterviewSession: vi.fn(),
  getActiveInterviewSession: vi.fn(),
  sendInterviewMessage: vi.fn(),
  flushInterviewSession: vi.fn(),
  closeInterviewSession: vi.fn()
}));

import {
  createInterviewSession,
  getActiveInterviewSession,
  sendInterviewMessage
} from "@/lib/api/interview";

const mockedCreateInterviewSession = vi.mocked(createInterviewSession);
const mockedGetActiveInterviewSession = vi.mocked(getActiveInterviewSession);
const mockedSendInterviewMessage = vi.mocked(sendInterviewMessage);

describe("useInterviewSession", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("sets session_conflict with recoverableSessionId on create conflict", async () => {
    mockedCreateInterviewSession.mockRejectedValueOnce(
      new ApiRequestError({
        code: "SESSION_CONFLICT",
        message: "conflict",
        retryable: true,
        details: { existing_session_id: "sess-existing" }
      })
    );

    const { result } = renderHook(() => useInterviewSession());

    await act(async () => {
      await result.current.create("alice");
    });

    expect(result.current.state).toBe("session_conflict");
    expect(result.current.recoverableSessionId).toBe("sess-existing");
    expect(result.current.error?.code).toBe("SESSION_CONFLICT");
  });

  it("maps send SESSION_NOT_FOUND to session_not_found state", async () => {
    mockedCreateInterviewSession.mockResolvedValueOnce({
      session_id: "sess-1",
      thread_id: "thread-1",
      username: "alice",
      created_at: "2026-01-01T00:00:00Z"
    });
    mockedSendInterviewMessage.mockRejectedValueOnce(
      new ApiRequestError({
        code: "SESSION_NOT_FOUND",
        message: "missing",
        retryable: false
      })
    );

    const { result } = renderHook(() => useInterviewSession());

    await act(async () => {
      await result.current.create("alice");
    });

    await act(async () => {
      await result.current.send("hello");
    });

    expect(result.current.state).toBe("session_not_found");
    expect(result.current.error?.code).toBe("SESSION_NOT_FOUND");
  });

  it("syncFromServerEvent ignores mismatched session and updates on matching one", async () => {
    mockedCreateInterviewSession.mockResolvedValueOnce({
      session_id: "sess-1",
      thread_id: "thread-1",
      username: "alice",
      created_at: "2026-01-01T00:00:00Z"
    });

    const { result } = renderHook(() => useInterviewSession());

    await act(async () => {
      await result.current.create("alice");
    });

    act(() => {
      result.current.syncFromServerEvent("processing", "sess-other");
    });
    expect(result.current.state).toBe("connected");

    act(() => {
      result.current.syncFromServerEvent("message_processed", "sess-1");
    });
    expect(result.current.state).toBe("ready_for_next_turn");
  });

  it("recovers from active session while create request is still pending", async () => {
    vi.useFakeTimers();

    mockedCreateInterviewSession.mockImplementationOnce(
      () =>
        new Promise(() => {
          // keep pending to simulate a browser/proxy that never resolves POST in time
        }),
    );
    mockedGetActiveInterviewSession
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        session_id: "sess-recovered",
        thread_id: "thread-recovered",
        username: "alice",
        created_at: "2026-01-01T00:00:00Z",
      });

    const { result } = renderHook(() =>
      useInterviewSession({
        initialUsername: "alice",
      }),
    );

    await act(async () => {
      const pending = result.current.create("alice");
      await vi.advanceTimersByTimeAsync(300);
      await pending;
    });

    expect(result.current.session?.session_id).toBe("sess-recovered");
    expect(result.current.state).toBe("connected");
  });
});
