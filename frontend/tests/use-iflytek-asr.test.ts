import { describe, expect, it } from "vitest";

import { splitFinalWordsByRole } from "@/lib/hooks/use-iflytek-asr";

describe("splitFinalWordsByRole", () => {
  it("splits a finalized result when rl changes mid-sentence", () => {
    const { segments, lastRole } = splitFinalWordsByRole(
      [
        { w: "我", wp: "n", rl: "1" },
        { w: "刚", wp: "n" },
        { w: "说", wp: "n" },
        { w: "完", wp: "n" },
        { w: "你", wp: "n", rl: "2" },
        { w: "来", wp: "n" },
        { w: "问", wp: "n" },
      ],
      0
    );

    expect(segments).toEqual([
      { text: "我刚说完", roleNumber: 1, rawRl: 1, isFinal: true },
      { text: "你来问", roleNumber: 2, rawRl: 2, isFinal: true },
    ]);
    expect(lastRole).toBe(2);
  });

  it("keeps rl=0 words on the previous speaker when no new role appears", () => {
    const { segments, lastRole } = splitFinalWordsByRole(
      [
        { w: "继", wp: "n" },
        { w: "续", wp: "n" },
        { w: "追", wp: "n" },
        { w: "问", wp: "n" },
      ],
      2
    );

    expect(segments).toEqual([
      { text: "继续追问", roleNumber: 2, rawRl: 0, isFinal: true },
    ]);
    expect(lastRole).toBe(2);
  });
});
