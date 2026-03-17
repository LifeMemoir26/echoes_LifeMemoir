import { describe, expect, it } from "vitest";

import { clearSavedSession, getSavedUsername, saveSessionUsername } from "@/lib/auth/token";

describe("auth/token helpers", () => {
  it("stores the last authenticated username only", () => {
    saveSessionUsername("alice");
    expect(getSavedUsername()).toBe("alice");
  });

  it("clears the persisted username", () => {
    saveSessionUsername("alice");
    clearSavedSession();
    expect(getSavedUsername()).toBeNull();
  });
});
