import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { useGenerateTimeline } from "@/lib/hooks/use-generate-timeline";

const generateTimelineMock = vi.fn();

vi.mock("@/lib/api/timeline", () => ({
  generateTimeline: (...args: unknown[]) => generateTimelineMock(...args)
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useGenerateTimeline", () => {
  beforeEach(() => {
    generateTimelineMock.mockReset();
  });

  it("handles success and stores last request snapshot", async () => {
    generateTimelineMock.mockResolvedValueOnce({
      username: "alice",
      timeline: [{ title: "a" }],
      event_count: 1,
      generated_at: "2026-01-01T00:00:00",
      trace_id: "timeline-ok"
    });

    const { result } = renderHook(() => useGenerateTimeline(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submit({ username: "alice", ratio: 0.2 });
    });

    expect(result.current.phase).toBe("success");
    expect(result.current.data?.event_count).toBe(1);
    expect(result.current.lastRequest?.username).toBe("alice");
  });

  it("maps retryable and non-retryable errors", async () => {
    generateTimelineMock.mockRejectedValueOnce(
      new ApiRequestError({ code: "TEMP", message: "temporary", retryable: true, traceId: "t-1" })
    );

    const { result } = renderHook(() => useGenerateTimeline(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.submit({ username: "alice", ratio: 0.3 });
    });

    expect(result.current.phase).toBe("error");
    expect(result.current.error?.code).toBe("TEMP");
    expect(result.current.canRetry).toBe(true);

    generateTimelineMock.mockRejectedValueOnce(
      new ApiRequestError({ code: "INVALID", message: "invalid", retryable: false, traceId: "t-2" })
    );

    await act(async () => {
      await result.current.retry();
    });

    expect(result.current.error?.code).toBe("INVALID");
    expect(result.current.canRetry).toBe(false);
  });

  it("enforces single in-flight submit", async () => {
    let resolveRequest: ((value: unknown) => void) | undefined;
    generateTimelineMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        })
    );

    const { result } = renderHook(() => useGenerateTimeline(), { wrapper: createWrapper() });

    await act(async () => {
      const first = result.current.submit({ username: "alice", ratio: 0.2 });
      const second = result.current.submit({ username: "alice", ratio: 0.2 });
      expect(await second).toBeNull();
      resolveRequest?.({
        username: "alice",
        timeline: [],
        event_count: 0,
        generated_at: "2026-01-01T00:00:00",
        trace_id: "timeline-done"
      });
      await first;
    });

    expect(generateTimelineMock).toHaveBeenCalledTimes(1);
  });
});
