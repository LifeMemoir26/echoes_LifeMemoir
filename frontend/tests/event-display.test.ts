import { describe, expect, it } from "vitest";

import { formatEventYearLabel } from "@/lib/utils/event-display";

describe("formatEventYearLabel", () => {
  it("returns year for normal years", () => {
    expect(formatEventYearLabel("1998", "春季")).toBe("1998");
  });

  it("uses time_detail when year is 9999", () => {
    expect(formatEventYearLabel("9999", "大学期间")).toBe("大学期间");
  });

  it("falls back gracefully when year is 9999 but time_detail is empty", () => {
    expect(formatEventYearLabel("9999", "  ")).toBe("时间待补充");
  });
});
