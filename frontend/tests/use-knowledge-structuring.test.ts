import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/knowledge", () => ({
  triggerReprocess: vi.fn(),
  cancelStructuring: vi.fn()
}));

import { triggerReprocess } from "@/lib/api/knowledge";
import { useKnowledgeStructuring } from "@/lib/hooks/use-knowledge-structuring";

const mockedTriggerReprocess = vi.mocked(triggerReprocess);

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

function makeSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    }
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" }
  });
}

describe("useKnowledgeStructuring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows trigger error when triggerReprocess fails", async () => {
    mockedTriggerReprocess.mockRejectedValueOnce(new Error("boom"));

    const { result } = renderHook(() => useKnowledgeStructuring("mat-1"), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.trigger();
    });

    expect(result.current.isProcessing).toBe(false);
    expect(result.current.stage).toBeNull();
    expect(result.current.error).toBe("boom");
  });

  it("consumes SSE status and error events to finish with error state", async () => {
    mockedTriggerReprocess.mockResolvedValueOnce({ material_id: "mat-1", trace_id: "trace-1" });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      makeSseResponse([
        'event: status\ndata: {"label":"提取事件"}\n\n',
        'event: error\ndata: {"message":"解析失败"}\n\n'
      ])
    );

    const { result } = renderHook(() => useKnowledgeStructuring("mat-1"), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.trigger();
    });

    await waitFor(() => {
      expect(result.current.isProcessing).toBe(false);
    });

    expect(result.current.stage).toBeNull();
    expect(result.current.error).toBe("解析失败");
  });
});
