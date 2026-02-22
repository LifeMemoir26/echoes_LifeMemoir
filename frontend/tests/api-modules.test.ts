import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api/client";
import { createInterviewSession, sendInterviewMessage } from "@/lib/api/interview";
import { generateMemoir } from "@/lib/api/memoir";
import { generateTimeline } from "@/lib/api/timeline";

type MockResponse = {
  status: number;
  text: () => Promise<string>;
};

function jsonResponse(payload: unknown, status = 200): MockResponse {
  return {
    status,
    text: async () => JSON.stringify(payload)
  };
}

describe("api modules", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates interview session with typed contract", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        status: "success",
        data: {
          session_id: "sess-1",
          thread_id: "thread-1",
          username: "alice",
          created_at: "2026-02-19T09:00:00Z"
        },
        errors: []
      })
    );

    const data = await createInterviewSession({ username: "alice" });

    expect(data.session_id).toBe("sess-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/session/create",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("maps interview message error into ApiRequestError", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          status: "failed",
          data: null,
          errors: [
            {
              error_code: "SESSION_NOT_FOUND",
              error_message: "session does not exist or has expired",
              retryable: false,
              trace_id: "session-abc",
              error_details: {}
            }
          ]
        },
        404
      )
    );

    await expect(
      sendInterviewMessage("sess-missing", { speaker: "user", content: "hello" })
    ).rejects.toMatchObject({
      name: "ApiRequestError",
      normalized: expect.objectContaining({ code: "SESSION_NOT_FOUND", retryable: false, traceId: "session-abc" })
    });
  });

  it("requests timeline endpoint with abort signal support", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        status: "success",
        data: {
          username: "alice",
          timeline: [],
          event_count: 0,
          generated_at: "2026-02-19T09:00:00Z",
          trace_id: "timeline-1"
        },
        errors: []
      })
    );

    const controller = new AbortController();
    const data = await generateTimeline({ username: "alice", auto_save: false }, controller.signal);

    expect(data.trace_id).toBe("timeline-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/generate/timeline",
      expect.objectContaining({ method: "POST", signal: controller.signal })
    );
  });

  it("maps aborted timeline request to retryable REQUEST_ABORTED", async () => {
    fetchMock.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    await expect(generateTimeline({ username: "alice" })).rejects.toMatchObject({
      name: "ApiRequestError",
      normalized: expect.objectContaining({ code: "REQUEST_ABORTED", retryable: true })
    });
  });

  it("treats malformed timeline success data as CONTRACT_ERROR", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        status: "success",
        data: {
          username: "alice",
          // missing timeline/event_count/generated_at/trace_id
          broken: true
        },
        errors: []
      })
    );

    try {
      await generateTimeline({ username: "alice" });
      throw new Error("expected generateTimeline to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiRequestError);
      expect(error).toMatchObject({
        normalized: expect.objectContaining({ code: "CONTRACT_ERROR", retryable: false })
      });
    }
  });

  it("treats malformed memoir success data as CONTRACT_ERROR", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        status: "success",
        data: {
          username: "alice",
          memoir: "x"
          // missing length/generated_at/trace_id
        },
        errors: []
      })
    );

    await expect(generateMemoir({ username: "alice" })).rejects.toMatchObject({
      normalized: expect.objectContaining({ code: "CONTRACT_ERROR", retryable: false })
    });
  });
});
