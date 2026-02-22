import React from "react";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { useInterviewSession } from "@/lib/hooks/use-interview-session";

const createMock = vi.fn();
const sendMock = vi.fn();
const flushMock = vi.fn();
const closeMock = vi.fn();

vi.mock("@/lib/api/interview", () => ({
  createInterviewSession: (...args: unknown[]) => createMock(...args),
  sendInterviewMessage: (...args: unknown[]) => sendMock(...args),
  flushInterviewSession: (...args: unknown[]) => flushMock(...args),
  closeInterviewSession: (...args: unknown[]) => closeMock(...args)
}));

describe("useInterviewSession", () => {
  beforeEach(() => {
    createMock.mockReset();
    sendMock.mockReset();
    flushMock.mockReset();
    closeMock.mockReset();
  });

  it("exposes recoverable session id on SESSION_CONFLICT and supports recover", async () => {
    createMock.mockRejectedValueOnce(
      new ApiRequestError({
        code: "SESSION_CONFLICT",
        message: "active session already exists",
        retryable: false,
        details: { existing_session_id: "sess-existing-1" }
      })
    );

    const { result } = renderHook(() => useInterviewSession(), {
      wrapper: ({ children }: { children: React.ReactNode }) => <>{children}</>
    });

    await act(async () => {
      await result.current.create("alice");
    });

    expect(result.current.state).toBe("session_conflict");
    expect(result.current.recoverableSessionId).toBe("sess-existing-1");

    await act(async () => {
      result.current.recoverFromConflict("sess-existing-1", "alice");
    });

    expect(result.current.session?.session_id).toBe("sess-existing-1");
    expect(result.current.state).toBe("connected");
  });
});
