import { afterEach, describe, expect, it, vi } from "vitest";

import { connectInterviewSse } from "@/lib/api/interview-sse";

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

describe("api/interview-sse connect errors", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps FastAPI detail envelope and preserves error_code", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            status: "failed",
            data: null,
            errors: [
              {
                error_code: "FORBIDDEN_USERNAME",
                error_message: "denied",
                retryable: false,
                trace_id: "trace-1",
                error_details: { source: "sse" }
              }
            ]
          }
        }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      )
    );

    await expect(connectInterviewSse({ sessionId: "sess-1" }, () => undefined)).rejects.toMatchObject({
      normalized: {
        code: "FORBIDDEN_USERNAME",
        message: "denied",
        retryable: false,
        traceId: "trace-1",
        details: { source: "sse" }
      }
    });
  });

  it("falls back to SSE_CONNECT_FAILED when response is not contract JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("bad gateway", { status: 502 }));

    await expect(connectInterviewSse({ sessionId: "sess-1" }, () => undefined)).rejects.toMatchObject({
      normalized: {
        code: "SSE_CONNECT_FAILED",
        retryable: true
      }
    } satisfies Partial<ApiRequestError>);
  });

  it("parses initial context event with session_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      makeSseResponse([
        'id: 0\nevent: context\ndata: {"session_id":"sess-1","trace_id":"thread-1","pending_events":{"total":0,"priority_count":0,"unexplored_count":0,"events":[]}}\n\n'
      ])
    );

    const events: Array<{ event: string; data: Record<string, unknown> }> = [];
    const handle = await connectInterviewSse({ sessionId: "sess-1" }, (evt) => {
      events.push({ event: evt.event, data: evt.data as Record<string, unknown> });
    });
    await handle.done;

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      event: "context",
      data: {
        session_id: "sess-1",
        trace_id: "thread-1"
      }
    });
  });
});
