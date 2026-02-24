import { describe, expect, it } from "vitest";

import { isTokenExpired } from "@/lib/auth/token";

function createJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "none", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.`;
}

describe("auth/token helpers", () => {
  it("returns true for malformed token", () => {
    expect(isTokenExpired("not-a-jwt")).toBe(true);
  });

  it("returns false when exp missing", () => {
    expect(isTokenExpired(createJwt({ sub: "alice" }))).toBe(false);
  });

  it("checks exp correctly", () => {
    const now = Math.floor(Date.now() / 1000);
    expect(isTokenExpired(createJwt({ exp: now + 600 }))).toBe(false);
    expect(isTokenExpired(createJwt({ exp: now - 600 }))).toBe(true);
  });
});
