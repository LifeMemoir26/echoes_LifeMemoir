import { describe, expect, it } from "vitest";

import {
  ApiRequestError,
  ContractError,
  isApiError,
  normalizeUnknownError,
  parseEnvelope
} from "@/lib/api/client";

describe("api/client contract helpers", () => {
  it("validates ApiError shape", () => {
    expect(
      isApiError({
        error_code: "X",
        error_message: "msg",
        retryable: false,
        trace_id: "t1"
      })
    ).toBe(true);

    expect(isApiError({ error_code: "X" })).toBe(false);
  });

  it("parses valid envelope", () => {
    const envelope = parseEnvelope<{ id: number }>({
      status: "success",
      data: { id: 1 },
      errors: []
    });

    expect(envelope.status).toBe("success");
    expect(envelope.data?.id).toBe(1);
  });

  it("throws ContractError for malformed envelope", () => {
    expect(() => parseEnvelope({ status: "ok", data: null, errors: [] })).toThrow(ContractError);
  });

  it("normalizes ApiRequestError directly", () => {
    const normalized = normalizeUnknownError(
      new ApiRequestError({ code: "FORBIDDEN", message: "denied", retryable: false, traceId: "t2" }),
      "fallback"
    );

    expect(normalized).toEqual({
      code: "FORBIDDEN",
      message: "denied",
      retryable: false,
      traceId: "t2"
    });
  });

  it("maps fetch/network style errors", () => {
    const normalized = normalizeUnknownError(new Error("Failed to fetch"), "fallback");

    expect(normalized.code).toBe("NETWORK_ERROR");
    expect(normalized.retryable).toBe(true);
  });
});
