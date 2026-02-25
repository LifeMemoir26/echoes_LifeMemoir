import { describe, expect, it } from "vitest";

import { formatArchiveAtHour, resolveMaterialDisplayName } from "@/lib/knowledge/material-display-name";

describe("resolveMaterialDisplayName", () => {
  it("always shows interview materials as fixed label without timestamp", () => {
    expect(
      resolveMaterialDisplayName({
        material_type: "interview",
        display_name: "采访记录_20260225T091800",
        filename: "raw-name.txt",
      })
    ).toBe("采访记录");
  });

  it("uses display_name for non-interview files", () => {
    expect(
      resolveMaterialDisplayName({
        material_type: "document",
        display_name: "我的文档名",
        filename: "raw.txt",
      })
    ).toBe("我的文档名");
  });
});

describe("formatArchiveAtHour", () => {
  it("formats UTC ISO time to UTC+8 hour precision", () => {
    expect(formatArchiveAtHour("2026-02-25T01:18:59Z")).toBe("2026-02-25 09:00");
  });

  it("treats db timestamp without timezone as UTC and renders UTC+8", () => {
    expect(formatArchiveAtHour("2026-02-25 03:00:00")).toBe("2026-02-25 11:00");
  });
});
