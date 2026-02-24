import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    apiPost: vi.fn(),
    apiGet: vi.fn(),
    apiPostWithSignal: vi.fn(),
  };
});

import { ApiRequestError, apiGet, apiPostWithSignal } from "@/lib/api/client";
import { generateTimeline, getSavedTimeline } from "@/lib/api/generate";

const mockedApiGet = vi.mocked(apiGet);
const mockedApiPostWithSignal = vi.mocked(apiPostWithSignal);

describe("api/generate contract checks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("throws CONTRACT_ERROR when generateTimeline returns malformed data", async () => {
    mockedApiPostWithSignal.mockResolvedValueOnce({
      username: "alice",
      timeline: [],
      event_count: "1",
      generated_at: "2026-01-01T00:00:00Z",
      trace_id: "trace-1"
    } as unknown as never);

    await expect(generateTimeline({ username: "alice" })).rejects.toMatchObject({
      normalized: {
        code: "CONTRACT_ERROR"
      }
    });
  });

  it("returns null directly for absent saved timeline", async () => {
    mockedApiGet.mockResolvedValueOnce(null as never);

    await expect(getSavedTimeline()).resolves.toBeNull();
  });

  it("throws CONTRACT_ERROR when saved timeline payload shape is invalid", async () => {
    mockedApiGet.mockResolvedValueOnce({
      username: "alice",
      timeline: [],
      generated_at: "2026-01-01T00:00:00Z",
      trace_id: "trace-1"
    } as unknown as never);

    try {
      await getSavedTimeline();
      throw new Error("expected to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiRequestError);
      expect((error as ApiRequestError).normalized.code).toBe("CONTRACT_ERROR");
    }
  });
});
