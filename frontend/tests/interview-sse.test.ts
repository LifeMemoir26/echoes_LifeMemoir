import { afterEach, describe, expect, it, vi } from "vitest";

import { connectInterviewSse } from "@/lib/api/interview-sse";

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
});
