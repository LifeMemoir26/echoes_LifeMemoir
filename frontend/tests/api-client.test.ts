import { describe, expect, it } from "vitest";
import { ApiRequestError, ContractError, normalizeApiError, parseEnvelope } from "@/lib/api/client";

describe("parseEnvelope", () => {
  it("parses success envelope", () => {
    const result = parseEnvelope<{ memoir: string }>({
      status: "success",
      data: { memoir: "text" },
      errors: []
    });

    expect(result.status).toBe("success");
    expect(result.data?.memoir).toBe("text");
  });

  it("throws on malformed envelope", () => {
    expect(() =>
      parseEnvelope({
        status: "success",
        data: { memoir: "text" },
        errors: [{ error_code: "X" }]
      })
    ).toThrow(ContractError);
  });
});

describe("error normalization", () => {
  it("maps retryable semantics", () => {
    const normalized = normalizeApiError({
      error_code: "TEMPORARY",
      error_message: "try again",
      retryable: true,
      trace_id: "memoir-abc"
    });

    expect(normalized.retryable).toBe(true);
    expect(normalized.traceId).toBe("memoir-abc");

    const err = new ApiRequestError(normalized);
    expect(err.normalized.code).toBe("TEMPORARY");
  });
});
