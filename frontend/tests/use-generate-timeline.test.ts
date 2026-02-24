import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createElement, type ReactNode } from "react";

import { ApiRequestError } from "@/lib/api/client";
import { useGenerateTimeline } from "@/lib/hooks/use-generate-timeline";

vi.mock("@/lib/api/generate", () => ({
  generateTimeline: vi.fn(),
  getSavedTimeline: vi.fn(),
}));

const setTimelineCache = vi.fn();

vi.mock("@/lib/workspace/context", () => ({
  useWorkspaceContext: () => ({
    timelineCache: null,
    setTimelineCache,
  }),
}));

import { generateTimeline, getSavedTimeline } from "@/lib/api/generate";

const mockedGenerateTimeline = vi.mocked(generateTimeline);
const mockedGetSavedTimeline = vi.mocked(getSavedTimeline);

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const Wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}

describe("useGenerateTimeline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSavedTimeline.mockResolvedValue(null);
  });

  it("submits timeline generation and caches success state", async () => {
    mockedGenerateTimeline.mockResolvedValueOnce({
      username: "alice",
      timeline: [
        {
          event_id: 1,
          time: "2001",
          objective_summary: "summary",
          detailed_narrative: "detail",
        },
      ],
      event_count: 1,
      generated_at: "2026-01-01T00:00:00Z",
      trace_id: "trace-1",
    });

    const { result } = renderHook(() => useGenerateTimeline(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "alice" });
    });

    await waitFor(() => {
      expect(result.current.phase).toBe("success");
    });

    expect(result.current.data?.event_count).toBe(1);
    expect(setTimelineCache).toHaveBeenCalled();
  });

  it("exposes canRetry only for retryable errors", async () => {
    mockedGenerateTimeline.mockRejectedValueOnce(
      new ApiRequestError({
        code: "NETWORK_ERROR",
        message: "network",
        retryable: true,
      }),
    );

    const { result } = renderHook(() => useGenerateTimeline(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.submit({ username: "alice", ratio: 0.5 });
    });

    await waitFor(() => {
      expect(result.current.phase).toBe("error");
    });

    expect(result.current.canRetry).toBe(true);

    mockedGenerateTimeline.mockRejectedValueOnce(
      new ApiRequestError({
        code: "FORBIDDEN",
        message: "denied",
        retryable: false,
      }),
    );

    await act(async () => {
      result.current.reset();
      await result.current.submit({ username: "alice" });
    });

    await waitFor(() => {
      expect(result.current.phase).toBe("error");
    });
    expect(result.current.canRetry).toBe(false);
  });

  it("does not start a second submit while first request is pending", async () => {
    let resolveFirst:
      | ((value: {
          username: string;
          timeline: never[];
          event_count: number;
          generated_at: string;
          trace_id: string;
        }) => void)
      | null = null;
    mockedGenerateTimeline.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    );

    const { result } = renderHook(() => useGenerateTimeline(), {
      wrapper: createWrapper(),
    });

    let firstPromise: Promise<unknown> | null = null;
    act(() => {
      firstPromise = result.current.submit({ username: "alice" });
    });

    await waitFor(() => {
      expect(result.current.isPending).toBe(true);
    });

    let secondResult: unknown;
    await act(async () => {
      secondResult = await result.current.submit({ username: "alice" });
    });

    expect(secondResult).toBeNull();
    expect(mockedGenerateTimeline).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst?.({
        username: "alice",
        timeline: [],
        event_count: 0,
        generated_at: "2026-01-01T00:00:00Z",
        trace_id: "trace-1",
      });
      await firstPromise;
    });
  });
});
